import sympy as sp
from sympy import MatrixSymbol, BlockMatrix
from deap import gp, creator, base, tools
from evostencils import types
from evostencils.expressions import scalar, block
import operator
import itertools


class Individual:
    def __init__(self, tree1, tree2):
        self.tree1 = gp.PrimitiveTree(tree1)
        self.tree2 = gp.PrimitiveTree(tree2)


def initIterate(container, generator):
    return container(generator(), generator())


class ExpressionGenerator:

    def __init__(self, A: BlockMatrix, x: BlockMatrix, b: BlockMatrix):
        self._A = A
        self._x = x
        self._b = b
        self._symbols = []
        self._types = []
        self._symbol_types = {self._A: types.generate_matrix_type(self._A.shape)}
        self._symbol_names = {self._A: 'A'}
        self._primitive_set = gp.PrimitiveSetTyped("main", [], types.generate_matrix_type(self._A.shape))
        self._init_terminals()
        self._init_operators()
        self._init_creator()
        self._init_toolbox()

    def _init_terminals(self):
        A = self.A
        self.add_terminal(A, self.get_symbol_type(A), 'A')
        identity_matrix = sp.Identity(self.x.shape[0])
        self.add_terminal(identity_matrix, types.generate_diagonal_matrix_type(A.shape), 'I')
        self.add_terminal(block.get_diagonal(A), types.generate_diagonal_matrix_type(A.shape), 'A_d')
        self.add_terminal(block.get_lower_triangle(A), types.generate_strictly_lower_triangular_matrix_type(A.shape), 'A_l')
        self.add_terminal(block.get_upper_triangle(A), types.generate_strictly_upper_triangular_matrix_type(A.shape), 'A_u')

    def _init_operators(self):
        A = self.A
        GeneralMatrixType = types.generate_matrix_type(A.shape)
        DiagonalMatrixType = types.generate_diagonal_matrix_type(scalar.get_diagonal(self.A).shape)

        StrictlyLowerTriangularMatrixType = \
            types.generate_strictly_lower_triangular_matrix_type(scalar.get_lower_triangle(self.A).shape)
        StrictlyUpperTriangularMatrixType = \
            types.generate_strictly_upper_triangular_matrix_type(scalar.get_upper_triangle(self.A).shape)
        LowerTriangularMatrixType = \
            types.generate_lower_triangular_matrix_type(scalar.get_lower_triangle(self.A).shape)
        UpperTriangularMatrixType = \
            types.generate_upper_triangular_matrix_type(scalar.get_upper_triangle(self.A).shape)

        matrix_addition = operator.add
        operator_name = 'add'
        for argument_types in itertools.product(self.get_matrix_types, repeat=2):
            if argument_types[0] == argument_types[1]:
                self.add_operator(matrix_addition, argument_types, argument_types[0], operator_name)
            elif (argument_types[0] == DiagonalMatrixType and issubclass(argument_types[1], LowerTriangularMatrixType)) \
                    or (argument_types[1] == DiagonalMatrixType and issubclass(argument_types[0], LowerTriangularMatrixType)):
                self.add_operator(matrix_addition, argument_types, LowerTriangularMatrixType, operator_name)
            elif (argument_types[0] == DiagonalMatrixType and issubclass(argument_types[1], UpperTriangularMatrixType)) \
                    or (argument_types[1] == DiagonalMatrixType and issubclass(argument_types[0], UpperTriangularMatrixType)):
                self.add_operator(matrix_addition, argument_types, UpperTriangularMatrixType, operator_name)
            else:
                self.add_operator(matrix_addition, argument_types, GeneralMatrixType, operator_name)

        matrix_subtraction = operator.sub
        operator_name = 'sub'
        for argument_types in itertools.product(self.get_matrix_types, repeat=2):
            if (argument_types[0] == DiagonalMatrixType and issubclass(argument_types[1], LowerTriangularMatrixType)) \
                    or (argument_types[1] == DiagonalMatrixType and issubclass(argument_types[0], LowerTriangularMatrixType)):
                self.add_operator(matrix_subtraction, argument_types, LowerTriangularMatrixType, operator_name)
            elif (argument_types[0] == DiagonalMatrixType and issubclass(argument_types[1], UpperTriangularMatrixType)) \
                    or (argument_types[1] == DiagonalMatrixType and issubclass(argument_types[0], UpperTriangularMatrixType)):
                self.add_operator(matrix_subtraction, argument_types, UpperTriangularMatrixType, operator_name)
            else:
                self.add_operator(matrix_subtraction, argument_types, GeneralMatrixType, operator_name)

        matrix_multiplication = operator.mul
        operator_name = 'mul'
        for argument_types in itertools.product(self.get_matrix_types, repeat=2):
            if argument_types[0] == DiagonalMatrixType:
                self.add_operator(matrix_multiplication, argument_types, argument_types[1], operator_name)
            elif argument_types[0] == argument_types[1]:
                self.add_operator(matrix_multiplication, argument_types, argument_types[1], operator_name)
            else:
                self.add_operator(matrix_multiplication, argument_types, GeneralMatrixType, operator_name)

        matrix_transpose = sp.MatrixExpr.transpose
        operator_name = 'transpose'

        for argument_type in self.get_matrix_types:
            if issubclass(argument_type, LowerTriangularMatrixType):
                self.add_operator(matrix_transpose, [argument_type], UpperTriangularMatrixType, operator_name)
            elif issubclass(argument_type, UpperTriangularMatrixType):
                self.add_operator(matrix_transpose, [argument_type], LowerTriangularMatrixType, operator_name)
            else:
                self.add_operator(matrix_transpose, [argument_type], argument_type, operator_name)

        matrix_inverse = sp.MatrixExpr.inverse
        operator_name = 'inverse'

        for argument_type in self.get_matrix_types:
            if argument_type == DiagonalMatrixType:
                self.add_operator(matrix_inverse, [argument_type], argument_type, operator_name)
            elif issubclass(argument_type, LowerTriangularMatrixType):
                self.add_operator(matrix_inverse, [argument_type], GeneralMatrixType, operator_name)
            elif issubclass(argument_type, UpperTriangularMatrixType):
                self.add_operator(matrix_inverse, [argument_type], GeneralMatrixType, operator_name)


    @staticmethod
    def _init_creator():
        creator.create("Individual", Individual)
        #creator.create("Individual", gp.PrimitiveTree)

    def _init_toolbox(self):
        self._toolbox = base.Toolbox()
        self._toolbox.register("expr", gp.genHalfAndHalf, pset=self._primitive_set, min_=1, max_=4)
        self._toolbox.register("individual", initIterate, Individual, self._toolbox.expr)
        #self._toolbox.register("individual", tools.initIterate, creator.Individual, self._toolbox.expr)
        self._toolbox.register("population", tools.initRepeat, list, self._toolbox.individual)

    def set_matrix_type(self, symbol, matrix_type):
        self._symbol_types[symbol] = matrix_type

    def get_symbol_type(self, symbol):
        return self._symbol_types[symbol]

    @property
    def A(self) -> BlockMatrix:
        return self._A

    @property
    def x(self) -> BlockMatrix:
        return self._x

    @property
    def b(self) -> BlockMatrix:
        return self._b

    @property
    def get_symbols(self) -> list:
        return self._symbols

    @property
    def get_matrix_types(self) -> list:
        return self._types

    def add_terminal(self, symbol, matrix_type, name=None):
        self._symbols.append(symbol)
        self._types.append(matrix_type)
        self._symbol_types[symbol] = matrix_type
        if name:
            self._symbol_names[symbol] = name
            self._primitive_set.addTerminal(symbol, matrix_type, name=name)
        else:
            self._symbol_names[symbol] = str(symbol)
            self._primitive_set.addTerminal(symbol, matrix_type, name=str(symbol))

    def add_terminal_list(self, symbols: list, matrix_types: list):
        assert not matrix_types or len(symbols) == len(matrix_types), \
            "Either no or the appropriate number of types must be provided"
        if not matrix_types:
            for symbol in symbols:
                if isinstance(symbol, types.DiagonalMatrixSymbol):
                    self.add_terminal(symbol, types.generate_diagonal_matrix_type(symbol.shape))
                elif isinstance(symbol, types.LowerTriangularMatrixSymbol):
                    self.add_terminal(symbol, types.generate_strictly_lower_triangular_matrix_type(symbol.shape))
                elif isinstance(symbol, types.UpperTriangularMatrixSymbol):
                    self.add_terminal(symbol, types.generate_strictly_upper_triangular_matrix_type(symbol.shape))
                else:
                    self.add_terminal(symbol, types.generate_matrix_type(symbol.shape))
        else:
            for (symbol, matrix_type) in zip(symbols, matrix_types):
                self.add_terminal(symbol, matrix_type)

    def add_operator(self, primitive, argument_types, result_type, name: str):
        self._primitive_set.addPrimitive(primitive, argument_types, result_type, name)

    def generate_individual(self):
        return self._toolbox.individual()

    def compile_expression(self, expression):
        return sp.block_collapse(gp.compile(expression, self._primitive_set))
