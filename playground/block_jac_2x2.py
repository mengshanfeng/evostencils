from lfa_lab import *
import matplotlib.pyplot as plt

grid = Grid(2, [1.0/32, 1.0/32])

# Define the discrete Laplace operator
a = [ ((-1,0),-1), ((0, -1), -1),
      ((0,0), 4), ((0,1), -1), ((1,0), -1) ]
A = operator.from_stencil(a, grid)

d = block_jacobi(A, (2, 2))
# Define the block diagonal part of A
d = NdArray(shape=(2, 1))
d[0,0] = [((0,0), 4), ((1,0), 0)]
d[1,0] = [((0,0), 4), ((-1,0), 0)]

#d = NdArray(shape=(1, 1))
#d[0,0] = [((0,0), 4)]

#d = NdArray(shape=(2,2))
#d[0,0] = [ ((0,0), 4), ((0,1), -1), ((1,0), -1) ]
#d[0,1] = [ ((0,-1), -1), ((0,0), 4), ((1,0), -1) ]
#d[1,0] = [ ((-1,0), -1), ((0,0), 4), ((0,1), -1) ]
#d[1,1] = [ ((-1,0), -1), ((0,-1), -1), ((0,0), 4) ]
D = operator.from_periodic_stencil(d, grid)

# Define the block Jacobi error propagation operator
omega = 0.8
I = operator.identity(grid)
E = (I - omega * D.inverse() * A)
P_stencil = gallery.ml_interpolation_stencil(grid, grid.coarse((2,2)))
R_stencil = gallery.fw_restriction_stencil(grid, grid.coarse((2,2)))

print(E.symbol().spectral_radius())

#plot.plot_2d(E, norm_type='output')
#plt.show()




