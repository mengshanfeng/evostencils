from evostencils.expressions import base, multigrid as mg
from evostencils.stencils import constant


class CycleStorage:
    def __init__(self, level, grid):
        self.level = level
        self.grid = grid
        self.solution = Field(f'Solution', level, self)
        self.solution_tmp = Field(f'Solution_tmp', level, self)
        self.rhs = Field(f'RHS', level, self)
        self.rhs_tmp = Field(f'RHS_tmp', level, self)
        self.residual = Field(f'Residual', level, self)
        self.correction = Field(f'Correction', level, self)


class Field:
    def __init__(self, name=None, level=None, cycle_storage=None):
        self.name = name
        self.level = level
        self.cycle_storage = cycle_storage
        self.valid = False

    def to_exa3(self):
        if self.level > 0:
            return f'{self.name}@(finest - {self.level})'
        else:
            return f'{self.name}@finest'


class ProgramGenerator:
    def __init__(self, op: base.Operator, grid: base.Grid, rhs: base.Grid, dimension, coarsening_factor,
                 interpolation, restriction):
        self._operator = op
        self._grid = grid
        self._rhs = rhs
        self._dimension= dimension
        self._coarsening_factor = coarsening_factor
        self._interpolation = interpolation
        self._restriction = restriction

    @property
    def operator(self):
        return self._operator

    @property
    def grid(self):
        return self._grid

    @property
    def rhs(self):
        return self._rhs

    @property
    def dimension(self):
        return self._dimension

    @property
    def coarsening_factor(self):
        return self._coarsening_factor

    @property
    def interpolation(self):
        return self._interpolation

    @property
    def restriction(self):
        return self._restriction

    @property
    def interpolation_stencil_generator(self):
        return self._interpolation.stencil_generator

    @property
    def restriction_stencil_generator(self):
        return self._restriction.stencil_generator

    def generate(self, expression: mg.Cycle):
        coarsest_level = self.obtain_coarsest_level(expression)
        storages = self.generate_storage(coarsest_level)
        expression.storage = storages[0].solution
        self.assign_storage_to_subexpressions(expression, storages, 0)
        program = "Domain global < [0.0, 0.0] to [1.0, 1.0] >\n"
        program += self.add_field_declarations_to_program_string(program, storages)
        program += '\n'
        program = self.add_operator_declarations_to_program_string(program, coarsest_level)
        program += '\n'
        program += f'Function Cycle@finest {{\n'
        program += self.generate_multigrid(expression, storages)
        program += f'}}\n'
        program += '\n'
        program += self.generate_solver_function("gen_solve", storages)
        program += "\nApplicationHint {\n\tl4_genDefaultApplication = true\n}\n"
        return program

    @staticmethod
    def obtain_coarsest_level(cycle: mg.Cycle) -> int:
        def recursive_descent(expression: base.Expression, current_size: tuple, current_level: int):
            if isinstance(expression, mg.Cycle):
                if expression.grid.size < current_size:
                    new_size = expression.grid.size
                    new_level = current_level + 1
                else:
                    new_size = current_size
                    new_level = current_level
                level_iterate = recursive_descent(expression.iterate, new_size, new_level)
                level_correction = recursive_descent(expression.correction, new_size, new_level)
                return max(level_iterate, level_correction)
            elif isinstance(expression, mg.Residual):
                level_iterate = recursive_descent(expression.iterate, current_size, current_level)
                level_rhs = recursive_descent(expression.rhs, current_size, current_level)
                return max(level_iterate, level_rhs)
            elif isinstance(expression, base.BinaryExpression):
                level_operand1 = recursive_descent(expression.operand1, current_size, current_level)
                level_operand2 = recursive_descent(expression.operand2, current_size, current_level)
                return max(level_operand1, level_operand2)
            elif isinstance(expression, base.UnaryExpression):
                return recursive_descent(expression.operand, current_size, current_level)
            elif isinstance(expression, base.Scaling):
                return recursive_descent(expression.operand, current_size, current_level)
            elif isinstance(expression, base.Entity):
                return current_level
            else:
                raise RuntimeError("Unexpected expression")
        return recursive_descent(cycle, cycle.grid.size, 0) + 1

    def generate_storage(self, maximum_level):
        tmps = []
        grid = self.grid
        for level in range(0, maximum_level + 1):
            tmps.append(CycleStorage(level, grid))
            grid = mg.get_coarse_grid(grid, self.coarsening_factor)
        return tmps

    @staticmethod
    def needs_storage(expression: base.Expression):
        return expression.shape[1] == 1

    @staticmethod
    def adjust_storage_index(node, storages, i) -> int:
        if node.grid.size > storages[i].grid.size:
            return i-1
        elif node.grid.size < storages[i].grid.size:
            return i+1
        else:
            return i

    # Warning: This function modifies the expression passed to it
    @staticmethod
    def assign_storage_to_subexpressions(node: base.Expression, storages: [CycleStorage], i: int):
        if isinstance(node, mg.Cycle):
            i = ProgramGenerator.adjust_storage_index(node, storages, i)
            node.iterate.storage = storages[i].solution_tmp
            node.rhs.storage = storages[i].rhs_tmp
            node.correction.storage = storages[i].correction
            ProgramGenerator.assign_storage_to_subexpressions(node.iterate, storages, i)
            ProgramGenerator.assign_storage_to_subexpressions(node.correction, storages, i)
        elif isinstance(node, mg.Residual):
            i = ProgramGenerator.adjust_storage_index(node, storages, i)
            node.iterate.storage = storages[i].solution_tmp
            node.rhs.storage = storages[i].rhs_tmp
            ProgramGenerator.assign_storage_to_subexpressions(node.iterate, storages, i)
            ProgramGenerator.assign_storage_to_subexpressions(node.rhs, storages, i)
        elif isinstance(node, base.BinaryExpression):
            operand1 = node.operand1
            operand2 = node.operand2
            if ProgramGenerator.needs_storage(operand2):
                i = ProgramGenerator.adjust_storage_index(operand2, storages, i)
                if isinstance(operand2, mg.Residual):
                    operand2.storage = storages[i].residual
                else:
                    operand2.storage = storages[i].correction
            ProgramGenerator.assign_storage_to_subexpressions(operand1, storages, i)
            ProgramGenerator.assign_storage_to_subexpressions(operand2, storages, i)
        elif isinstance(node, base.UnaryExpression) or isinstance(node, base.Scaling):
            operand = node.operand
            if ProgramGenerator.needs_storage(operand):
                i = ProgramGenerator.adjust_storage_index(operand, storages, i)
                operand.storage = storages[i].correction
        elif isinstance(node, base.RightHandSide):
            i = ProgramGenerator.adjust_storage_index(node, storages, i)
            node.storage = storages[i].rhs
        elif isinstance(node, base.Grid) or isinstance(node, base.ZeroGrid):
            i = ProgramGenerator.adjust_storage_index(node, storages, i)
            node.storage = storages[i].solution

    @staticmethod
    def add_field_declarations_to_program_string(program_string: str, storages: [CycleStorage]):

        for i, storage in enumerate(storages):
            solution = storage.solution.to_exa3()
            solution_tmp = storage.solution_tmp.to_exa3()
            rhs = storage.rhs.to_exa3()
            rhs_tmp = storage.rhs_tmp.to_exa3()
            residual = storage.residual.to_exa3()
            correction = storage.correction.to_exa3()
            program_string += f'Field {solution} with Real on Node of global = 0.0\n'
            # TODO handle boundary condition
            if i == 0:
                program_string += f'Field {solution} on boundary = ' \
                                  f'( cos ( ( PI * vf_boundaryPosition_0@(finest - {storage.solution.level})@[0, 0] ) ) - ' \
                                  f'sin ( ( ( 2.0 * PI ) * vf_boundaryPosition_1@{storage.solution.level}@[0, 0] ) ) )\n'
            else:
                program_string += f'Field {solution} on boundary = 0.0\n'

            program_string += f'Field {solution_tmp} with Real on Node of global = 0.0\n'
            program_string += f'Field {solution_tmp} on boundary = 0.0\n'
            # TODO handle rhs
            program_string += f'Field {rhs} with Real on Node of global = ' \
                              f'( ( ( PI ** 2 ) * cos ( ( PI * vf_nodePosition_0@(finest - {storage.rhs.level})@[0, 0] ) ) ) - ' \
                              f'( ( 4.0 * ( PI ** 2 ) ) * sin ( ( ( 2.0 * PI ) * ' \
                              f'vf_nodePosition_1@(finest - {storage.rhs.level})@[0, 0] ) ) ) )\n'
            program_string += f'Field {rhs} on boundary = 0.0\n'

            program_string += f'Field {rhs_tmp} with Real on Node of global = 0.0\n'
            program_string += f'Field {rhs_tmp} on boundary = 0.0\n'

            program_string += f'Field {residual} with Real on Node of global = 0.0\n'
            program_string += f'Field {residual} on boundary = 0.0\n'

            program_string += f'Field {correction} with Real on Node of global = 0.0\n'
            program_string += f'Field {correction} on boundary = 0.0\n'
        return program_string

    @staticmethod
    def add_constant_stencil_to_program_string(program_string: str, level: int, operator_name: str, stencil: constant.Stencil):
        program_string += f"Operator {operator_name}@(finest - {level}) from Stencil {{\n"
        indent = '\t'
        for offset, value in stencil.entries:
            program_string += indent
            program_string += '['
            for i, _ in enumerate(offset):
                program_string += f'i{i}'
                if i < len(offset) - 1:
                    program_string += ', '
            program_string += f'] from ['
            for i, o in enumerate(offset):
                if o == 0:
                    program_string += f'i{i}'
                else:
                    program_string += f'(i{i} + ({o}))'
                if i < len(offset) - 1:
                    program_string += ', '
            program_string += f'] with {value}\n'
        program_string += '}\n'
        return program_string

    def add_operator_declarations_to_program_string(self, program_string: str, maximum_level: int):
        grid = self.grid
        for i in range(maximum_level + 1):
            stencil = self.operator.stencil_generator(grid)
            grid = mg.get_coarse_grid(grid, self.coarsening_factor)
            program_string = self.add_constant_stencil_to_program_string(program_string, i, self.operator.name, stencil)

        if self.interpolation_stencil_generator is None:
            program_string += f"Operator {self.interpolation.name} from default prolongation on Node with 'linear'\n"
        else:
            grid = self.grid
            for i in range(maximum_level):
                stencil = self.interpolation_stencil_generator(grid)
                # TODO generate string for stencil
                grid = mg.get_coarse_grid(grid, self.coarsening_factor)

        if self.restriction_stencil_generator is None:
            program_string += f"Operator {self.restriction.name} from default restriction on Node with 'linear'\n"
        else:
            grid = self.grid
            for i in range(maximum_level):
                stencil = self.restriction_stencil_generator(grid)
                # TODO generate string for stencil
                grid = mg.get_coarse_grid(grid, self.coarsening_factor)

        return program_string

    @staticmethod
    def determine_operator_level(operator, storages) -> int:
        for storage in storages:
            if operator.grid.size == storage.grid.size:
                return storage.level
        raise RuntimeError("No fitting level")

    def generate_coarse_grid_solver(self, expression: base.Expression, storages: [CycleStorage]):
        # TODO replace hard coded RB-GS by generic implementation
        level = expression.storage.level
        i = storages[-1].level
        n = 100
        program = f'\t{storages[i].solution_tmp.to_exa3()} = {storages[i].solution.to_exa3()}\n'
        program += f'\trepeat {n} times {{\n'
        program += f'\t\t{storages[i].solution_tmp.to_exa3()} = ((0.8 * diag_inv({self.operator.name}@(finest - {level}))) * ' \
                   f'({expression.storage.to_exa3()} - ({self.operator.name}@(finest - {level}) * ' \
                   f'{storages[i].solution_tmp.to_exa3()}))) where (((i0 + i1) % 2) == 0)\n'
        program += f'\t\t{storages[i].solution_tmp.to_exa3()} = ((0.8 * diag_inv({self.operator.name}@(finest - {level}))) * ' \
                   f'({expression.storage.to_exa3()} - ({self.operator.name}@(finest - {level}) * ' \
                   f'{storages[i].solution_tmp.to_exa3()}))) where (((i0 + i1) % 2) == 1)'
        program += '\n\t}\n'
        program += f'\t{expression.storage.to_exa3()} = {storages[i].solution_tmp.to_exa3()}\n'
        return program

    def generate_multigrid(self, expression: base.Expression, storages) -> str:
        program = ''
        if expression.storage is not None and expression.storage.valid:
            expression.storage.valid = False

        if isinstance(expression, mg.Cycle):
            program = self.generate_multigrid(expression.iterate, storages)
            if not expression.rhs.storage.valid:
                program += self.generate_multigrid(expression.rhs, storages)
                expression.rhs.storage.valid = True
            program += self.generate_multigrid(expression.correction, storages)
            field = expression.storage
            program += f'\t{field.to_exa3()} = ' \
                       f'{expression.iterate.storage.to_exa3()} + ' \
                       f'{expression.weight} * {expression.correction.storage.to_exa3()}\n'
        elif isinstance(expression, mg.Residual):
            program += f'\t{expression.storage.to_exa3()} = {expression.rhs.storage.to_exa3()} - ' \
                       f'{self.generate_multigrid(expression.operator, storages)} * ' \
                       f'{expression.iterate.storage.to_exa3()}\n'
        elif isinstance(expression, base.BinaryExpression):
            if isinstance(expression, base.Multiplication):
                operator_str = "*"
            elif isinstance(expression, base.Addition):
                operator_str = "+"
            elif isinstance(expression, base.Subtraction):
                operator_str = "-"

            if expression.storage is None:
                return f'{self.generate_multigrid(expression.operand1, storages)} ' \
                       f'{operator_str} ' \
                       f'{self.generate_multigrid(expression.operand2, storages)}'
            else:
                operand1 = expression.operand1
                operand2 = expression.operand2
                if expression.operand1.storage is None:
                    if isinstance(operand1, mg.CoarseGridSolver):
                        program += self.generate_multigrid(operand2, storages) + self.generate_coarse_grid_solver(expression, storages)
                        return program
                    else:
                        tmp1 = self.generate_multigrid(operand1, storages)
                else:
                    program += self.generate_multigrid(operand1, storages)
                    tmp1 = f'{operand1.storage.to_exa3()}'

                if expression.operand2.storage is None:
                    tmp2 = self.generate_multigrid(operand2, storages)
                else:
                    program += self.generate_multigrid(operand2, storages)
                    tmp2 = f'{operand2.storage.to_exa3()}'
                program += f'\t{expression.storage.to_exa3()} = {tmp1} {operator_str} {tmp2}\n'
        elif isinstance(expression, base.Scaling):
            program = ""
            operand = expression.operand
            field = expression.storage
            if field is None:
                tmp = self.generate_multigrid(expression.operand, storages)
            else:
                program += self.generate_multigrid(expression.operand, storages)
                tmp = f'{operand.storage.to_exa()}'
            program += f'{expression.factor} * {tmp}'
        elif isinstance(expression, base.Inverse):
            program = f'inverse({self.generate_multigrid(expression.operand, storages)})'
        elif isinstance(expression, base.Diagonal):
            program = f'diag({self.generate_multigrid(expression.operand, storages)})'
        elif isinstance(expression, mg.Restriction):
            level_offset = self.determine_operator_level(expression, storages) - 1
            program = f'{expression.name}@(finest - {level_offset})'
        elif isinstance(expression, mg.Interpolation):
            level_offset = self.determine_operator_level(expression, storages) + 1
            program = f'{expression.name}@(finest - {level_offset})'
        elif isinstance(expression, base.Operator):
            program = f'{expression.name}@(finest - {self.determine_operator_level(expression, storages)})'
        elif isinstance(expression, base.Grid):
            pass
            #program = f'{expression.storage.to_exa3()}'
        else:
            print(type(expression))
            raise NotImplementedError("Case not implemented")
        return f'{program}'

    @staticmethod
    def generate_l2_norm_residual(function_name: str, storages: [CycleStorage]) -> str:
        residual = storages[0].residual.to_exa3()
        program = ""
        program += f"Function {function_name}@finest : Real {{\n"
        program += f"\tVar gen_resNorm : Real = 0.0\n"
        program += f"\tgen_resNorm += dot ( {residual}, {residual} )\n"
        program += f"\treturn sqrt ( gen_resNorm )\n"
        program += f"}}\n"
        return program

    def generate_solver_function(self, function_name: str, storages: [CycleStorage], maximum_number_of_iterations=1000) -> str:
        assert maximum_number_of_iterations >= 1, "At least one iteration required"
        operator = f"{self.operator.name}@finest"
        solution = storages[0].solution.to_exa3()
        rhs = storages[0].rhs.to_exa3()
        residual = storages[0].residual.to_exa3()
        compute_residual_norm = "gen_resNorm"
        program = self.generate_l2_norm_residual(compute_residual_norm, storages)
        program += f"\nFunction {function_name}@finest {{\n"
        program += f"\t{residual} = ({rhs} - ({operator} * {solution}))\n"
        program += f"\tVar gen_initRes: Real = {compute_residual_norm}@finest()\n"
        program += f"\tVar gen_curRes: Real = gen_initRes\n"
        program += f"\tVar gen_prevRes: Real = gen_curRes\n"
        program += f'\tprint("Starting residual:", gen_initRes)\n'
        program += f"\tVar gen_curIt : Integer = 0\n"
        program += f"\trepeat until(((gen_curIt >= {maximum_number_of_iterations}) || (gen_curRes <= (1.0E-10 * gen_initRes))) || (gen_curRes <= 0.0)) {{\n"
        program += f"\t\tgen_curIt += 1\n" \
                   f"\t\tCycle@finest()\n"
        program += f"\t\t{residual} = ({rhs} - ({operator} * {solution}))\n"
        program += f"\t\tgen_prevRes = gen_curRes\n"
        program += f"\t\tgen_curRes = {compute_residual_norm}@finest()\n"
        program += f'\t\tprint("Residual after", gen_curIt, "iterations is", gen_curRes, "--- convergence factor is", (gen_curRes / gen_prevRes))'
        program += "\t}\n"
        program += "}\n"
        return program

    @staticmethod
    def write_program_to_file(name: str, program: str):
        with open(f'{name}.exa3', "w") as file:
            print(program, file=file)

    @staticmethod
    def generate_settings_file(name: str):
        tmp = f'user\t="Guest"\n\n'
        tmp = f'basePathPrefix\t="./"\n\n'
        tmp = f'l3file\t="{name}.exa3"\n\n'
        tmp = f'debugL3File\t="Debug/{name}_debug.exa3"\n'
        tmp = f'debugL4File\t="Debug/{name}_debug.exa4"\n\n'
        tmp = f'htmlLogFile\t="Debug/{name}_log.html"\n\n'
        tmp = f'outputPath\t="generated/{name}"\n\n'
        tmp = f'produceHtmlLog\t=true\n'
        tmp = f'timeStrategies\t=true\n\n'
        tmp = f'buildfileGenerators=\t={{"MakefileGenerator"}}\n'
        with open(f'{name}.settings', "w") as file:
            print(tmp, file=file)

