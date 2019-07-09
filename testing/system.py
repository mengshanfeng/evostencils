from evostencils.expressions import base, system, multigrid, transformations, partitioning
from evostencils.stencils.gallery import *
import lfa_lab
from evostencils.evaluation.convergence import ConvergenceEvaluatorSystem

dimension = 2
min_level = 2
max_level = 10
size = 2**max_level
grid_size = (size, size)
h = 1/(2**max_level)
step_size = (h, h)
coarsening_factor = (2, 2)
coarsening_factors = [coarsening_factor, coarsening_factor]
grid = base.Grid(grid_size, step_size)
us = base.ZeroApproximation(grid)
vs = base.ZeroApproximation(grid)
f_u = base.RightHandSide('f_u', grid)
f_v = base.RightHandSide('f_v', grid)

problem_name = 'poisson_2D_constant'
stencil_generator = Poisson2D()
interpolation_generator = MultilinearInterpolationGenerator(coarsening_factor)
restriction_generator = FullWeightingRestrictionGenerator(coarsening_factor)

laplace = base.Operator('Laplace', grid, stencil_generator)
I = base.Identity(grid)
Z = base.ZeroOperator(grid)


A = system.Operator('A', [[laplace, I], [Z, laplace]])
u = system.Approximation('u', [vs, us])
f = system.RightHandSide('f', [f_v, f_u])
res = multigrid.Residual(A, u, f)
tmp = base.Multiplication(base.Inverse(system.Diagonal(A)), res)
u_new = multigrid.Cycle(u, f, tmp, weight=1, partitioning=partitioning.RedBlack)
res_new = multigrid.Residual(A, u_new, f)
coarse_grid = system.get_coarse_grid(u.grid, coarsening_factors)
R = system.Restriction('full-weighting restriction', u.grid, coarse_grid, restriction_generator)
P = system.Prolongation('multilinear interpolation', u.grid, coarse_grid, interpolation_generator)
A_c = system.get_coarse_operator(A, coarse_grid)
# A_c = base.Multiplication(base.Multiplication(R, A), P)

CGS = multigrid.CoarseGridSolver(A_c)
tmp = base.Multiplication(R, res_new)
tmp = base.Multiplication(CGS, tmp)
tmp = base.Multiplication(P, tmp)
u_new = multigrid.Cycle(u_new, f, tmp, partitioning=partitioning.Single)
iteration_matrix = transformations.get_system_iteration_matrix(u_new)
convergence_evaluator = ConvergenceEvaluatorSystem([lfa_lab.Grid(dimension, step_size), lfa_lab.Grid(dimension, step_size)], coarsening_factors, dimension)
lfa_node = convergence_evaluator.transform(iteration_matrix)
convergence_factor = convergence_evaluator.compute_spectral_radius(iteration_matrix)
print(f'Spectral radius: {convergence_factor}')
