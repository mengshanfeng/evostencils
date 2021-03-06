from evostencils.expressions import base, system, partitioning as part
from evostencils.stencils import constant, periodic


def generate_decoupled_jacobi(operator: system.Operator):
    return system.Diagonal(operator)


def generate_collective_jacobi(operator: system.Operator):
    return system.ElementwiseDiagonal(operator)


def generate_collective_block_jacobi(operator: system.Operator, block_sizes: [tuple]):
    entries = []
    for i, row in enumerate(operator.entries):
        entries.append([])
        for j, entry in enumerate(row):
            stencil = entry.generate_stencil()
            block_diagonal = periodic.block_diagonal(stencil, block_sizes[i])
            new_entry = base.Operator(f'{operator.name}_{i}{j}_block_diag', entry.grid, base.ConstantStencilGenerator(block_diagonal))
            entries[-1].append(new_entry)
    return system.Operator(f'{operator.name}_block_diag', entries)


def generate_decoupled_block_jacobi(operator: system.Operator, block_sizes: [tuple]):
    entries = []
    for i, row in enumerate(operator.entries):
        entries.append([])
        for j, entry in enumerate(row):
            if i == j:
                stencil = entry.generate_stencil()
                block_diagonal = periodic.block_diagonal(stencil, block_sizes)
                new_entry = base.Operator(f'{operator.name}_{i}{j}_block_diag', entry.grid,
                                          base.ConstantStencilGenerator(block_diagonal))
            else:
                new_entry = base.ZeroOperator(entry.grid)
            entries[-1].append(new_entry)
    return system.Operator(f'{operator.name}_block_diag', entries)
