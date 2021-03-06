from evostencils.expressions import base
from typing import List, Tuple


class Operator(base.Entity):

    def __init__(self, name, entries):
        self._name = name
        self._entries = entries
        shape = [0, 0]
        for row in entries:
            entry = row[0]
            shape[0] += entry.shape[0]
        for entry in entries[0]:
            shape[1] += entry.shape[1]
        self._shape = tuple(shape)
        super().__init__()

    @property
    def entries(self):
        return self._entries

    @property
    def grid(self):
        return list(map(lambda entry: entry.grid, self.entries[0]))


class ZeroOperator(Operator):
    def __init__(self, grid: [base.Grid], name='0'):
        entries = [[base.ZeroOperator(g) for g in grid] for _ in grid]
        super().__init__(name, entries)


class Identity(Operator):
    def __init__(self, grid: [base.Grid], name='I'):
        entries = []
        for i, _ in enumerate(grid):
            entries.append([])
            for j, g in enumerate(grid):
                if i == j:
                    entries[i].append(base.Identity(g))
                else:
                    entries[i].append(base.ZeroOperator(g))
        super().__init__(name, entries)


class Approximation(base.Entity):

    def __init__(self, name, entries):
        self._name = name
        self._entries = entries
        if len(entries) == 1:
            self._shape = entries[0].shape
        else:
            acc = 0
            for entry in entries:
                acc += entry.shape[0]
            self._shape = tuple((acc, entries[0].shape[1]))
        super().__init__()

    @property
    def entries(self):
        return self._entries

    @property
    def grid(self):
        return list(map(lambda entry: entry.grid, self.entries))

    @property
    def predecessor(self):
        return None


class RightHandSide(Approximation):
    pass


class ZeroApproximation(Approximation):
    def __init__(self, grid: [base.Grid], name='0'):
        super().__init__(name, [base.ZeroApproximation(g) for g in grid])


class InterGridOperator(Operator):
    def __init__(self, name, list_of_intergrid_operators, ZeroOperatorType):
        entries = [[intergrid_operator if i == j else ZeroOperatorType(intergrid_operator.fine_grid, intergrid_operator.coarse_grid)
                    for j in range(len(list_of_intergrid_operators))]for i, intergrid_operator in enumerate(list_of_intergrid_operators)]
        super().__init__(name, entries)


class Restriction(InterGridOperator):
    def __init__(self, name, list_of_intergrid_operators):
        super().__init__(name, list_of_intergrid_operators, base.ZeroRestriction)


class Prolongation(InterGridOperator):
    def __init__(self, name, list_of_intergrid_operators):
        super().__init__(name, list_of_intergrid_operators, base.ZeroProlongation)


class Diagonal(base.UnaryExpression):
    pass


class ElementwiseDiagonal(base.UnaryExpression):
    pass


def get_coarse_grid(grid: [base.Grid], coarsening_factors: List[Tuple[int, ...]]):
    return [base.get_coarse_grid(g, cf) for g, cf in zip(grid, coarsening_factors)]


def get_coarse_approximation(approximation: Approximation, coarsening_factors: List[Tuple[int, ...]]):
    return Approximation(f'{approximation.name}', [base.Approximation(f'{entry.name}_c', base.get_coarse_grid(entry.grid, cf))
                                                   for entry, cf in zip(approximation.entries, coarsening_factors)])


def get_coarse_rhs(rhs: RightHandSide, coarsening_factors: List[Tuple[int, ...]]):
    return RightHandSide(f'{rhs.name}', [base.RightHandSide(f'{entry.name}_c', base.get_coarse_grid(entry.grid, cf))
                                         for entry, cf in zip(rhs.entries, coarsening_factors)])


def get_coarse_operator(operator, coarse_grid):
    new_entries = [[base.Operator(f'{entry.name}_c', coarse_grid[i], entry.stencil_generator) for entry in row]
                   for i, row in enumerate(operator.entries)]
    return Operator(f'{operator.name}', new_entries)