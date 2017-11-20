

import time
import scipy
from scipy import interpolate
from matplotlib.lines import Line2D
import matplotlib.pyplot as plt
from random import randint
from scipy.sparse import *
from scipy import *
from scipy.sparse.linalg import spsolve
from scipy.sparse import hstack, vstack
from matplotlib import cm
from mpl_toolkits.mplot3d import Axes3D
import numpy as np

"""
Efficient-GMRF 

VERSION STATUS: 
Goal: Combine Solowjow-Paper GMRF with Xu et al. GMRF

Input:
(1) prior distribution of theta
(2) spatial sites S*, x_field, y_field
(3) extended sites S, x_grid, y_grid
(4) regression function f(.)
Output:
(1) predictive mean mue_xy
(2) predictive variance sig_xy_sq

Variables:
p := full latent field (z.T, betha.T)
"""

"""#####################################################################################"""
"""Initialize Experimental Setup"""
# Field size
x_min = 0
x_max = 10
y_min = 0
y_max = 5

# INITIALIZATION GMRF
lxf = 50  # Number of x-axis GMRF vertices inside field
lyf = 25
de = np.array([float(x_max - x_min)/(lxf-1), float(y_max - y_min)/(lyf-1)])  # Element width in x and y

dvx = 15  # Number of extra GMRF vertices at border of field
dvy = 15
xg_min = x_min - dvx * de[0]  # Min GMRF field value in x
xg_max = x_max + dvx * de[0]
yg_min = y_min - dvy * de[1]
yg_max = y_max + dvy * de[1]

lx = lxf + 2*dvx  # Total number of GMRF vertices in x
ly = lyf + 2*dvy
n = lx*ly  # Number of GMRF vertices
xf_grid = np.atleast_2d(np.linspace(x_min, x_max, lxf, endpoint=True)).T  # GMRF grid inside field
yf_grid = np.atleast_2d(np.linspace(y_min, y_max, lyf, endpoint=True)).T
x_grid = np.atleast_2d(np.linspace(xg_min, xg_max, lx, endpoint=True)).T  # Total GMRF grid
y_grid = np.atleast_2d(np.linspace(yg_min, yg_max, ly, endpoint=True)).T


"""#####################################################################################"""
"""TEMPERATURE FIELD (Ground truth)"""
def true_field(field_analytical):
    if field_analytical == True:
        """Analytic field"""
        z = np.array([[10, 10.625, 12.5, 15.625, 20],[5.625, 6.25, 8.125, 11.25, 15.625],[3, 3.125, 4, 12, 12.5],[5, 2, 3.125, 10, 10.625], [5, 8, 11, 12, 10]])
        X = np.atleast_2d([0, 2, 4, 6, 10])  # Specifies column coordinates of field
        Y = np.atleast_2d([0, 1, 3, 4, 5])  # Specifies row coordinates of field
        x_field = np.arange(x_min, x_max, 1e-2)
        y_field = np.arange(y_min, y_max, 1e-2)
        f = scipy.interpolate.interp2d(X, Y, z, kind='cubic')
        z_field = f(x_field, y_field)
        return x_field, y_field, z_field, f
    if field_analytical == False:
        """Field from GMRF"""
        car_var = [False]  # Use car(1)?
        kappa_field = [1]  # Kappa for Choi CAR(2) true field/ Solowjow et. al CAR(1)
        alpha_field = [0.01]  # Alpha for Choi CAR(2) true field/ Solowjow et. al CAR(1)

        z = sample_from_GMRF(lx, ly, kappa_field, alpha_field, car_var, 'True')  # GMRF as in paper
        X = np.linspace(xg_min, xg_max, num=lx, endpoint=True)  # Specifies column coordinates of field
        Y = np.linspace(yg_min, yg_max, num=ly, endpoint=True)  # Specifies row coordinates of field
        f = sci.interpolate.interp2d(X, Y, z, kind='cubic')

        x_field = np.arange(x_min, x_max, 1e-2)
        y_field = np.arange(y_min, y_max, 1e-2)
        z_field = f(x_field, y_field)
        return x_field, y_field, z_field, f
x_field, y_field, z_field, f = true_field(field_analytical=True)

""" Define field topology of the vector field values and precision matrix"""
def gmrf_Q(lx, ly, kappa, alpha, car1=False):

    field_info = np.arange(lx * ly).reshape((ly, lx))
    infmat = np.dot(-1, np.ones((lx * ly, 13)))

    # TORUS VERTICE TOPOLOGY
    # Define Observation matrix that map grid vertices to continuous measurement locations
    """ Indices for precision function of field i,j
                     a2,j
              a1,d1  a1,j  a1,c1
        i,d2   i,d1   i,j  i,c1    i,c2
              b1,d1  b1,j  b1,c1
                     b2,j
    """
    for ii in range(0, ly):
        for jj in range(0, lx):

            if (ii+2) <= (ly-1): a1 = ii+1; a2 = ii+2
            elif (ii+1) <= (ly-1): a1 = ii+1; a2 = 0
            else: a1 = 0; a2 = 1

            if (ii-2) >= 0: b1 = ii-1; b2 = ii-2
            elif (ii-1) >= 0: b1 = ii-1; b2 = ly-1
            else: b1 = ly-1; b2 = ly-2

            if (jj+2) <= (lx-1): c1 = jj+1; c2 = jj+2
            elif (jj+1) <= (lx-1): c1 = jj+1; c2 = 0
            else: c1 = 0; c2 = 1

            if (jj-2) >= 0: d1 = jj-1; d2 = jj-2
            elif (jj-1) >= 0: d1 = jj-1; d2 = lx-1
            else: d1 = lx-1; d2 = lx-2
            #                                        field i,j              a1,j             b1,j               i,c1             i,d1
            infmat[field_info[ii, jj], :] = np.array([field_info[ii, jj], field_info[a1, jj], field_info[b1, jj], field_info[ii, c1], field_info[ii, d1],
                                                            #               a2,j             b2,j               i,c2             i,d2
                                                                      field_info[a2, jj],field_info[b2, jj], field_info[ii, c2], field_info[ii, d2],
                                                            #               a1,c1            a1,d1               b1,d1           b1,c1
                                                                      field_info[a1,c1], field_info[a1,d1], field_info[b1,d1], field_info[b1,c1]])
    a = alpha + 4

    if car1 == True:
        Q_rc = np.zeros(shape=(3, 5 * lx * ly)).astype(int)  # Save Q in COO-sparse-format
        Q_d = np.zeros(shape=(3, 5 * lx * ly)).astype(float)  # Save Q in COO-sparse-format
        for i1 in range(0, (lx * ly)):
            a1 = int(5 * i1)
            Q_rc[0, a1:(a1 + 5)] = i1 * np.ones(shape=(1, 5))  # Row indices
            Q_rc[1, a1:(a1 + 5)] = np.hstack((i1, infmat[i1, 1:5]))  # Column indices
            Q_d[0, a1:(a1 + 5)] = np.hstack((a * (1 / kappa) * np.ones(shape=(1, 1)),
                                              -1 * (1/kappa) * np.ones(shape=(1, 4))))  # Data

        return Q_rc, Q_d
    else:
        Q_rc = np.zeros(shape=(3, 13 * lx * ly)).astype(int)  # Save Q in COO-sparse-format
        Q_d = np.zeros(shape=(3, 13 * lx * ly)).astype(float)  # Save Q in COO-sparse-format
        for i2 in range(0, (lx * ly)):
            a1 = int(13*i2)
            Q_rc[0, a1:(a1 + 13)] = i2*np.ones(shape=(1, 13))  # Row indices
            Q_rc[1, a1:(a1 + 13)] = np.hstack((i2, infmat[i2, 1:5], infmat[i2, 5:9], infmat[i2, 9:13]))  # Column indices
            Q_d[0, a1:(a1 + 13)] = np.hstack(((4 + a ** 2) * (1 / kappa) * np.ones(shape=(1, 1)), (-2 * a / kappa) * np.ones(shape=(1, 4)),
                                            (1/kappa) * np.ones(shape=(1, 4)), (2 / kappa) * np.ones(shape=(1, 4))))  # Data
        return Q_rc, Q_d

"""SAMPLE from GMRF"""
def sample_from_GMRF(lx1, ly1, kappa, alpha, car_var, plot_gmrf=False):
    # Calculate precision matrix
    #Q_storage = np.zeros(shape=(lx1 * ly1, lx1 * ly1, len(kappa)))
    d_Q_stor = []  # Create list to store Q matrices
    for i in range(len(kappa)):
        d_Q_stor.append(gmrf_Q(lx1, ly1, kappa[i], alpha[i], car1=car_var[i]))
    # Check Infmat and Q
    """
    print(ly, lx, ly*lx)
    print(infmat[0])
    print(infmat[24, :])
    print(infmat[24, 1:5])
    print(Q[i, infmat[i, 1:5].astype(int)] )
    print(Q[24, :])
    print(np.linalg.matrix_rank(Q, tol=None))
    """
    # Draw sampel from GMRF
    mue_Q = 10
    z_I = np.random.standard_normal(size=lx1 * ly1)
    x_Q = np.zeros(shape=(ly1, lx1, len(kappa)))

    for i in range(0, len(kappa)):
        L_Q = sci.sparse.linalg.splu(d_Q_stor["Q_stor{0}".format(i)])
        v_Q = L_Q.solve(z_I)
        x_Q_vec = mue_Q + v_Q
        x_Q[:, :, i] = x_Q_vec.reshape((ly1, lx1))

    if plot_gmrf == True:
        if len(kappa) == 1:
            fig, ax = plt.subplots(1)
            # ax = ax.ravel()
            k = 0
            cf = ax.pcolor(np.linspace(x_min, x_max, num=lx1, endpoint=True),
                                         np.linspace(y_min, y_max, num=ly1, endpoint=True), x_Q[:, :, k])
            ax.axis('tight')
            plt.colorbar(cf, ax=ax)
            ax.set_title('GMRF sample, kappa: ' + str(kappa[k]) + ', alpha: ' + str(alpha[k]))
            plt.xlabel('x (m)')
            plt.ylabel('y (m)')
            k += 1
            plt.show()
        else:
                fig, ax = plt.subplots(3, 2)
                k = 0
                for j in range(2):
                    for i in range(3):
                        cf = ax[i,j].pcolor(np.linspace(x_min, x_max, num=lx, endpoint=True),
                                        np.linspace(y_min, y_max, num=ly, endpoint=True), x_Q[:, :, k])
                        ax[i, j].axis('tight')
                        plt.colorbar(cf, ax=ax[i,j])
                        ax[i, j].set_title('GMRF sample, kappa: ' + str(kappa[k]) + ', alpha: ' + str(alpha[k]))
                    plt.xlabel('x (m)')
                    plt.ylabel('y (m)')
                    k += 1
                plt.show()

    return x_Q
"""# e. g.
car_var = [False, False, False, True, True, True]  # To which car() model corresponds the hyperparameters?
#kappa = [4, 1, 0.25]  # Kappa for CAR(2) from paper "Efficient Bayesian spatial"
#alpha = [0.0025, 0.01, 0.04]

#kappa = [1, 1, 1]  # Kappa for CAR(1)
#alpha = [0.1, 0.001, 0.00001]

kappa = [4, 1, 0.25, 1, 1, 1]  # Kappa for CAR(1) and CAR(2)
alpha = [0.0025, 0.01, 0.04, 0.1, 0.001, 0.00001]

sample_from_GMRF(lx, ly, kappa, alpha, car_var)
"""

"""Calculate new observation vector"""
def interpolation_matrix(x_local2):
    u1 = np.zeros(shape=(n + p, 1)).astype(float)
    nx = int((x_local2[0] - xg_min) / de[0])  # Calculates the vertice column x-number at which the shape element starts.
    ny = int((x_local2[1] - yg_min) / de[1])  # Calculates the vertice row y-number at which the shape element starts.

    # Calculate position value in element coord-sys in meters
    x_el = float(0.1 * (x_local2[0] / 0.1 - int(x_local2[0] / 0.1))) - de[0] / 2
    y_el = float(0.1 * (x_local2[1] / 0.1 - int(x_local2[1] / 0.1))) - de[1] / 2

    # Define shape functions, "a" is element width in x-direction
    u1[(ny * lx) + nx] = (1 / (de[0] * de[1])) * ((x_el - de[0] / 2) * (y_el - de[1] / 2))  # u for lower left corner
    u1[(ny * lx) + nx + 1] = (-1 / (de[0] * de[1])) * ((x_el + de[0] / 2) * (y_el - de[1] / 2))  # u for lower right corner
    u1[((ny + 1) * lx) + nx] = (-1 / (de[0] * de[1])) * ((x_el - de[0] / 2) * (y_el + de[1] / 2))  # u for upper left corner
    u1[((ny + 1) * lx) + nx + 1] = (1 / (de[0] * de[1])) * ((x_el + de[0] / 2) * (y_el + de[1] / 2))  # u for upper right corner
    return u1, np.array([nx, ny])

"""Calculate new observation vector"""
def observation_vector(x_local1, control_var, sigma_w_squ):
    # Define Observation vector that maps grid vertices to a continuous measurement location
    if control_var == False:  # Random observation vector
        nxf = randint(0, len(x_field))  # Measurement at random TRUE FIELD grid
        nyf = randint(0, len(y_field))
        s_obs = [y_field[nyf], x_field[nxf]]
    else: # Observation from actual auv state
        s_obs = [x_local1[1], x_local1[0]]

    sd_obs = [int((x_local1[1]) * 1e2), int((x_local1[0]) * 1e2)]
    y1 = np.array(z_field[sd_obs[0], sd_obs[1]]) + np.random.normal(loc=0.0, scale=sqrt(sigma_w_squ), size=1)
    # print('n_lu', n_lu, 'n_ru', n_ru, 'n_lo', n_lo, 'n_ro', n_ro )

    u1, xx = interpolation_matrix(x_local1)
    return u1, y1, s_obs

"""Define sparse matrix save and load"""
def save_sparse_csr(filename, array):
    # note that .npz extension is added automatically
    np.savez(filename, data=array.data, indices=array.indices,
             indptr=array.indptr, shape=array.shape)
def load_sparse_csr(filename):
    # here we need to add .npz extension manually
    loader = np.load(filename + '.npz')
    return csr_matrix((loader['data'], loader['indices'], loader['indptr']),
                      shape=loader['shape'])

"""Define AUV dynamics"""
def auv_dynamics(v_auv, x_auv, u_auv, epsilon_a, delta_t):
    x_auv_out = np.zeros(shape=(3))
    x_auv_out[0] = x_auv[0] + v_auv * cos(x_auv[2]) * delta_t
    x_auv_out[1] = x_auv[1] + v_auv * sin(x_auv[2]) * delta_t
    x_auv_out[2] = x_auv[2] + u_auv * delta_t + epsilon_a * sqrt(delta_t)

    # Prevent AUV from leaving the true field
    if x_auv_out[0] < 0:
        x_auv_out[0] = 0
    if x_auv_out[0] > x_field[-1]:
        x_auv_out[0] = x_field[-1]
    if x_auv_out[1] < 0:
        x_auv_out[1] = 0
    if x_auv_out[1] > y_field[-1]:
        x_auv_out[1] = y_field[-1]
    if x_auv_out[2] > 2*pi:
        x_auv_out[2] = x_auv[2] - 2*pi

    return x_auv_out


"""#####################################################################################"""
"""---------PI-GMRF CODE----------------------------------------------------------------"""

"""#######################################"""
"""Choose GMRF simulation parameters"""
carGMRF = [False]  # Use car(1)? Default is car(2) from Choi et al
Q_calc_var = False  # Re-Calculate precision matrix at Initialization? False: Load stored precision matrix
p = 1  # Number of regression coefficients beta
F = np.ones(shape=(n, p))  # Mean regression functions
T = 1e-6 * np.ones(shape=(p, p))  # Precision matrix of the regression coefficients
sigma_w_squ = 0.2 ** 2  # Measurement variance
sample_time_gmrf = 100  # Sample/Calculation time in ms of GMRF algorithm
simulation_end_time = 10000  # Run time of simulation in ms

"""#######################################"""
"""Choose control parameters"""
control_var = True  #

x_auv = np.array([5, 0.5, 0.5]).T  # Initial AUV state
v_auv = 0.5  # AUV velocity in meter/second (constant)

n_k = 15  # Number of virtual roll-out pathes
n_horizon = 15  # Control horizon length in s
N_horizon = 15  # Number of discrete rollout points
t_cstep = n_horizon / N_horizon  # Control horizon step size in s
sigma_epsilon = pi / 8  # Exploration noise in radians, 90 grad = 1,57
n_updates = 10  # Control loop updates
R_cost = 10 * np.ones(shape=(1, 1))  # Immediate control cost

"""#######################################"""
"""Define plot parameters"""
vmin = np.amin(z_field) - 0.5  # Minimum plotted mean and true field value?
vmax = np.amax(z_field) + 0.5  # Maximum plotted mean and true field value?
var_min = 0  # Minimum plotted variance value?
var_max = 5
levels = np.linspace(vmin, vmax, 20)  # How many contour levels for mean and true field?
PlotField = False  # Plot Torus margins of GMRF (GMRF-vertices aside the true field)?
LabelVertices = True  # Label all vertices by number? Only for >PlotField = True<
"""#######################################"""

"""Define hyperparameter prior"""
# Choi paper
#kappa_prior = np.array([0.0625 * (2 ** 0), 0.0625 * (2 ** 2), 0.0625 * (2 ** 4), 0.0625 * (2 ** 6), 0.0625 * (2 ** 8)]).astype(float)
#alpha_prior = np.array([0.000625 * (1 ** 2), 0.000625 * (2 ** 2), 0.000625 * (4 ** 2), 0.000625 * (8 ** 2), 0.000625 * (16 ** 2)]).astype(float)

# Choi Parameter (size 1)
#kappa_prior = np.array([0.0625 * (2 ** 4)]).astype(float)
#alpha_prior = np.array([0.000625 * (4 ** 2)]).astype(float)

# Choi Parameter (size 2)
kappa_prior = np.array([0.0625 * (2 ** 2), 0.0625 * (2 ** 4)]).astype(float)
alpha_prior = np.array([0.000625 * (2 ** 2), 0.000625 * (4 ** 2)]).astype(float)

# Choi Parameter (size 3)
#kappa_prior = np.array([0.0625 * (2 ** 2), 0.0625 * (2 ** 4), 0.0625 * (2 ** 6)]).astype(float)
#alpha_prior = np.array([0.000625 * (2 ** 2), 0.000625 * (4 ** 2), 0.000625 * (8 ** 2)]).astype(float)

# Solowjow Parameter for CAR(1) (size 1)
#kappa_prior = np.array([1]).astype(float)
#alpha_prior = np.array([0.01]).astype(float)

# Same theta values (size 5)
#kappa_prior = np.array([0.0625 * (2 ** 4), 0.0625 * (2 ** 4), 0.0625 * (2 ** 4), 0.0625 * (2 ** 4), 0.0625 * (2 ** 4)]).astype(float)
#alpha_prior = np.array([0.000625 * (4 ** 2), 0.000625 * (4 ** 2), 0.000625 * (4 ** 2), 0.000625 * (4 ** 2), 0.000625 * (4 ** 2)]).astype(float)

# Same theta values (size 10)
#kappa_prior = np.array([0.0625 * (2 ** 4), 0.0625 * (2 ** 4), 0.0625 * (2 ** 4), 0.0625 * (2 ** 4), 0.0625 * (2 ** 4), 0.0625 * (2 ** 4), 0.0625 * (2 ** 4), 0.0625 * (2 ** 4), 0.0625 * (2 ** 4), 0.0625 * (2 ** 4)]).astype(float)
#alpha_prior = np.array([0.000625 * (4 ** 2), 0.000625 * (4 ** 2), 0.000625 * (4 ** 2), 0.000625 * (4 ** 2), 0.000625 * (4 ** 2), 0.000625 * (4 ** 2), 0.000625 * (4 ** 2), 0.000625 * (4 ** 2), 0.000625 * (4 ** 2), 0.000625 * (4 ** 2)]).astype(float)

# Extended Choi paper
#kappa_prior = np.array([1000, 100, 10, 0.0625 * (2 ** 0), 0.0625 * (2 ** 2), 0.0625 * (2 ** 4), 0.0625 * (2 ** 6), 0.0625 * (2 ** 8), 0.0625 * (2 ** 9), 0.0625 * (2 ** 10)]).astype(float)
#alpha_prior = np.array([0.000625 * (1 ** -1), 0.000625 * (1 ** 0), 0.000625 * (1 ** 1), 0.000625 * (1 ** 2), 0.000625 * (2 ** 2), 0.000625 * (4 ** 2), 0.000625 * (8 ** 2), 0.000625 * (16 ** 2), 0.000625 * (32 ** 2), 0.000625 * (64 ** 2), 0.000625 * (128 ** 2)]).astype(float)
THETA = []  # Matrix containing all discrete hyperparameter combinations
for i in range(0, len(alpha_prior)):
    for j in range(0, len(kappa_prior)):
        THETA.append([kappa_prior[j], alpha_prior[i]])
THETA = np.array(THETA).T
l_TH = len(THETA[1])  # Number of hyperparameter pairs
p_THETA = 1.0 / l_TH  # Prior probability for one theta


time_start = time.time()
"""Initialize precision matrix for different thetas"""
diag_Q_t_inv = np.zeros(shape=(n+p, l_TH)).astype(float)
F_sparse = scipy.sparse.csr_matrix(F)
FT_sparse = scipy.sparse.csr_matrix(F.T)
T_inv = np.linalg.inv(T)  # Inverse of the Precision matrix of the regression coefficients
T_sparse = scipy.sparse.csr_matrix(T)
Tinv_sparse = scipy.sparse.csr_matrix(1/T)

if Q_calc_var == True:
    for jj in range(0, l_TH):
        #print("Initialization", jj)

        """Initialize Q_{x|eta}"""
        # _{field values|eta}             kappa          alpha
        Q_rc, Q_d = gmrf_Q(lx, ly, THETA[0, jj], THETA[1, jj], car1=carGMRF)
        Q_temporary = coo_matrix((Q_d[0, :], (Q_rc[0, :], Q_rc[1, :])), shape=(n, n)).tocsr()
        Q_check = Q_temporary.todense()
        Q_eta_inv = np.linalg.inv(coo_matrix((Q_d[0, :], (Q_rc[0, :], Q_rc[1, :])), shape=(n, n)).todense())

        """Q_{x|eta,y=/} & diag_Q_inv """
        A2 = Q_temporary.dot(-1 * F_sparse)
        B1 = -1 * FT_sparse.dot(Q_temporary)
        B2 = scipy.sparse.csr_matrix.dot(FT_sparse, Q_temporary.dot(F_sparse)) + T_sparse
        H1 = hstack([Q_temporary, A2])
        H2 = hstack([B1, B2])
        filename = "Q_t_" + str(jj)
        Q_t = scipy.sparse.vstack([H1, H2]).tocsr()
        save_sparse_csr(filename, Q_t)

        C1 = Q_eta_inv + np.dot(F, np.dot(T_inv, F.T))
        C2 = np.dot(F, T_inv)
        D1 = np.dot(F, T_inv).T
        Q_t_inv = np.vstack([np.hstack([C1, C2]),
                             np.hstack([D1, T_inv])])

        diag_Q_t_inv[:, jj] = Q_t_inv.diagonal()
    #np.save('diag_Q_t_inv.npy', diag_Q_t_inv)

    del A2, B1, B2, H1, H2, C1, C2, D1, Q_eta_inv, Q_t, Q_t_inv, Q_rc, Q_d, T_sparse, F_sparse, FT_sparse

else:
    print('Loading precalculated matrices')
    for j2 in range(0, l_TH):
        filename = "Q_t_pre_" + str(j2)
        Q_t2 = load_sparse_csr(filename)
        filename2 = "Q_t_" + str(j2)
        save_sparse_csr(filename2, Q_t2)

    diag_Q_t_inv = np.load('diag_Q_t_inv.npy')
    del T_sparse, F_sparse, FT_sparse


"""Initialize matrices and vectors"""
b = np.zeros(shape=(n+p, 1)) # Canonical mean
c = 0.0  # Log-likelihood update vector
h_theta = np.zeros(shape=(n+p, l_TH))
g_theta = np.zeros(shape=(l_TH, 1))
log_pi_y = np.zeros(shape=(l_TH, 1))
pi_theta = np.zeros(shape=(l_TH, 1))
mue_theta = np.zeros(shape=(n+p, l_TH))
mue_x = np.zeros(shape=(n+p, 1))
var_x = np.zeros(shape=(n+p, 1))

n_storage = 0
stored_mue_x = np.zeros(shape=(n+p, simulation_end_time/sample_time_gmrf))
stored_var_x = np.zeros(shape=(n+p, simulation_end_time/sample_time_gmrf))
stored_phi_theta = np.zeros(shape=(l_TH, simulation_end_time/sample_time_gmrf))
trajectory_1 = np.array(x_auv).reshape(1, 3)


"""Initialize u and epsilon for PI"""
R_cost_inv = np.linalg.inv(R_cost)  # Inverse of the Precision matrix of the regression coefficients
u_optimal = np.zeros(shape=(N_horizon, 1))
u_auv = np.zeros(shape=(N_horizon, n_k))
epsilon_auv = np.zeros(shape=(N_horizon, n_k))
tau_x = np.zeros(shape=(len(x_auv), N_horizon, n_k))
tau_optimal = np.zeros(shape=(len(x_auv), N_horizon))
var_x_tau = np.zeros(shape=(N_horizon, n_k))
control_cost = np.zeros(shape=(N_horizon, n_k))
exp_lambda_S = np.zeros(shape=(N_horizon, n_k))
S_tau = np.zeros(shape=(N_horizon, n_k))
P_tau = np.zeros(shape=(N_horizon, n_k))


"""Initialize ion plot"""
def initialize_plot():
    plt.ion()
    fig1 = plt.figure(figsize=(8, 3))

    ax0 = fig1.add_subplot(221)
    cp = plt.contourf(x_field, y_field, z_field, vmin=vmin, vmax=vmax, levels=levels)
    plt.colorbar(cp); plt.title('True Field'); plt.xlabel('x (m)'); plt.ylabel('y (m)')


    ax1 = fig1.add_subplot(222)
    plt.colorbar(cp); plt.xlabel('x (m)'); plt.ylabel('y (m)'); ax1.set_title('GMRF Mean')

    ax2 = fig1.add_subplot(223)
    c22 = plt.contourf(x_field, y_field, np.dot(np.diag(np.linspace(var_min, var_max, len(y_field), endpoint=True)), np.ones((len(y_field), len(x_field)))), 10, vmin=var_min, vmax=var_max)
    plt.xlabel('x (m)'); plt.ylabel('y (m)'); plt.colorbar(c22); ax2.set_title('GMRF Variance')

    _alpha_v, _kappa_v = np.meshgrid(alpha_prior, kappa_prior)
    alpha_v, kappa_v = _alpha_v.ravel(), _kappa_v.ravel()
    bottom = np.zeros_like(pi_theta)
    _x = _y = np.arange(len(alpha_prior))
    _xx, _yy = np.meshgrid(_x, _y)
    x, y = _xx.ravel(), _yy.ravel()
    colors = plt.cm.jet(np.arange(len(x)) / float(np.arange(len(x)).max()))

    ax3 = fig1.add_subplot(224, projection='3d')
    ticksx = np.arange(0.5, len(alpha_prior) + 0.5, 1)
    plt.xticks(ticksx, alpha_prior)
    plt.yticks(ticksx, kappa_prior)
    ax3.set_xlabel('alpha'); ax3.set_ylabel('kappa'); ax3.set_zlabel('p(theta)'); ax3.set_title('GMRF Hyperparameter Estimate')

    plt.draw()
    return fig1, ax0, ax1, ax2, ax3, x, y, bottom, colors
fig1, ax0, ax1, ax2, ax3, x, y, bottom, colors = initialize_plot()

"""#####################################################################################"""
"""START SIMULATION"""
time_2 = time.time()
print("--- %s seconds --- Initialization time" % (time_2 - time_start))

# Begin for-slope for all N observation at time t
for time_in_ms in range(0, simulation_end_time):  # 1200 ms sekunden


    """GAUSSIAN MARKOV RANDOM FIELD"""
    if time_in_ms % sample_time_gmrf < 0.0000001:
        time_3 = time.time()

        x_auv = auv_dynamics(v_auv, x_auv, u_optimal[0], 0, sample_time_gmrf/100)
        trajectory_1 = np.vstack([trajectory_1, x_auv])

        """Compute observation vector and observation"""
        u, y_t, s_obs = observation_vector(x_auv, control_var, sigma_w_squ)
        u_sparse = scipy.sparse.csr_matrix(u)

        """Update canonical mean and observation-dependent likelihood terms"""
        b = b + (y_t/sigma_w_squ) * u  # Canonical mean
        c = c - ((y_t ** 2) / (2 * sigma_w_squ))  # Likelihood term

        for jj in range(0, l_TH):
            """Calculate observation precision (?)"""
            filename = "Q_t_" + str(jj)
            Q_t = load_sparse_csr(filename)
            h_theta[:, jj] = scipy.sparse.linalg.spsolve(Q_t, u_sparse).T
            """Update Precision Matrix"""
            diag_Q_t_inv[:, jj] = np.subtract(diag_Q_t_inv[:, jj],  (np.multiply(h_theta[:, jj], h_theta[:, jj]) / (sigma_w_squ + np.dot(u.T, h_theta[:, jj]))))
            Q_t = Q_t + (1 / sigma_w_squ) * u_sparse.dot(u_sparse.T)
            save_sparse_csr(filename, Q_t)

            g_theta[jj] = g_theta[jj] - (0.5 * np.log(1 + (1 / sigma_w_squ) * np.dot(u.T, h_theta[:, jj])))
        # End for-slope for all N observation at time t

        for hh in range(0, l_TH):
            """Compute canonical mean"""
            mue_theta[:, hh] = scipy.sparse.linalg.spsolve(Q_t, b).T
            """Compute Likelihood"""
            log_pi_y[hh] = c + g_theta[hh] + 0.5 * np.dot(b.T, mue_theta[:, hh]) # - (1 / 2) * np.log(2*np.pi*sigma_w_squ)  # Compute likelihood

        """Scale likelihood and Posterior distribution (theta|y)"""
        log_pi_exp = np.exp(log_pi_y - np.amax(log_pi_y))
        posterior = (1 / np.sum(log_pi_exp)) * log_pi_exp * p_THETA
        pi_theta = (1 / np.sum(posterior)) * posterior  # Compute posterior distribution
        """Predictive mean and variance (x|y)"""
        for ji in range(0, n+p):
            mue_x[ji] = np.dot(mue_theta[[ji], :], pi_theta)  # Predictive Mean
            var_x[ji] = np.dot((diag_Q_t_inv[ji] + (np.subtract(mue_theta[ji, :], mue_x[ji] * np.ones(shape=(1, len(THETA[1])))) ** 2)),
                               pi_theta)

        # Store for plot
        stored_mue_x[:, [n_storage]] = mue_x
        stored_var_x[:, [n_storage]] = var_x
        stored_phi_theta[:, [n_storage]] = pi_theta
        time_4 = time.time()
        print("--- %s seconds --- GMRF algorithm time" % (time_4 - time_3))
        n_storage += 1



        """#####################################################################################"""
        """PATH INTEGRAL CONTROL"""
        u_optimal[:-1] = u_optimal[1:]
        u_optimal[-1] = 0

        for ii in range(0, n_updates):  # Repeat PI algorithm for convergence
            for jj in range(0, n_k):  # Iterate over all trajectories
                tau_x[:, 0, jj] = x_auv  # Set initial trajectory state
                # Calculate exploration noise (Only PI-Controller Hyperparameter)
                epsilon_auv[:, jj] = sigma_epsilon * np.random.standard_normal(N_horizon)

                for kk in range(0, N_horizon-1):  # Iterate over length of trajectory except of last entry
                    # Sample roll-out trajectory
                    print(kk,tau_x[:, 0, jj],'x_auv', x_auv)
                    tau_x[:, kk+1, jj] = auv_dynamics(v_auv, tau_x[:, kk, jj], u_optimal[kk], epsilon_auv[kk, jj], t_cstep)

                for kk in range(0, N_horizon):  # Iterate over length of trajectory
                    #g_m = np.array(1)
                    #M_m = (1 / np.dot(g_m.T, R_cost_inv.dot(g_m))) * np.dot(R_cost_inv, np.dot(g_m, g_m.T))
                    # Compute variance along sampled trajectory
                    M_m = 1  # Only for p=1 and this simple state model !
                    A_z, numb_ind = interpolation_matrix(tau_x[:, kk, jj])
                    var_x_tau[kk, jj] = np.dot(A_z.T, var_x)
                    control_cost[kk, jj] = 0.5 * np.dot(np.array(u_optimal[kk]+epsilon_auv[kk, jj]).T,
                                                        np.dot(R_cost, np.array(u_optimal[kk]+epsilon_auv[kk, jj])))

                for kk in range(0, N_horizon):  # Iterate over whole sampeld trajectory
                    S_tau[kk, jj] = np.sum(var_x_tau[kk:, jj]) + np.sum(control_cost[kk:, jj])
                for kk in range(0, N_horizon):  # Iterate over whole sampeld trajectory
                    exp_lambda_S[kk, jj] = exp(-10 * (S_tau[kk, jj] - np.amin(S_tau[:, jj])) /
                                               (np.amax(S_tau[:, jj]) - np.amin(S_tau[:, jj])))

            u_correction = np.zeros(shape=(N_horizon, 1))
            for kk in range(0, N_horizon):  # Iterate over length of trajectory
                for jj in range(0, n_k):  # Iterate over all trajectories
                    P_tau[kk, jj] = exp_lambda_S[kk, jj] / np.sum(exp_lambda_S[kk, :])
                for jj in range(0, n_k):  # Iterate over all trajectories
                    u_correction[kk] += P_tau[kk, jj] * M_m * epsilon_auv[kk, jj]

            u_optimal = u_optimal + u_correction


        tau_optimal[:, 0] = x_auv
        for kk in range(0, N_horizon - 1):  # Iterate over length of trajectory except of last entry
            tau_optimal[:, kk + 1] = auv_dynamics(v_auv, tau_x[:, kk, jj], u_optimal[kk], 0, t_cstep)

        # Random Walk
        #u_auv = ((0.2 * pi) / 1000) * randint(-500, 500)  # Control input for random walk
        #x_auv = auv_dynamics(v_auv, x_auv, u_auv, 0.01)


        """#####################################################################################"""
        """PLOT RESULTS"""
        # Transform mean and variance into matrix for scatter
        xv, yv = np.meshgrid(x_grid, y_grid)
        mue_x_plot = mue_x[0:(lx * ly)].reshape((ly, lx))
        var_x_plot = var_x[0:(lx * ly)].reshape((ly, lx))
        # Create vectors for enumerating the GMRF nodes
        xv_list = xv.reshape((lx * ly, 1))
        yv_list = yv.reshape((lx * ly, 1))
        labels = ['{0}'.format(i) for i in range(lx * ly)]  # Labels for annotating GMRF nodes

        # fig1 = plt.figure(figsize=(8, 3))

        """Plot True Field"""
        ax0 = fig1.add_subplot(221)
        cp = plt.contourf(x_field, y_field, z_field, vmin=vmin, vmax=vmax, levels=levels)
        plt.plot(x_auv[0], x_auv[1], marker='o', markerfacecolor='none')


        if PlotField == True:
            """Plot GMRF mean"""
            ax1 = fig1.add_subplot(222)
            c1 = ax1.contourf(np.linspace(xg_min, xg_max, num=lx, endpoint=True),
                              np.linspace(yg_min, yg_max, num=ly, endpoint=True),
                              mue_x_plot, vmin=vmin, vmax=vmax, levels=levels)
            plt.scatter(xv, yv, marker='+', facecolors='dimgrey')
            plt.plot([x_min, x_min, x_max, x_max, x_min], [y_min, y_max, y_max, y_min, y_min], "k")
            plt.plot(s_obs[1], s_obs[0], marker='o', markerfacecolor='none')

            if LabelVertices == True:
                # Label GMRF vertices
                for label, x, y in zip(labels, xv_list, yv_list):
                    plt.annotate(
                        label,
                        xy=(x, y), xytext=(-2, 2),
                        textcoords='offset points', ha='center', va='center',
                        # bbox=dict(boxstyle='round,pad=0.5', fc='yellow', alpha=0.5),
                        # arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0')
                    )

            """Plot GMRF variance"""
            ax2 = fig1.add_subplot(223)
            c2 = ax2.contourf(np.linspace(xg_min, xg_max, num=lx, endpoint=True),
                              np.linspace(yg_min, yg_max, num=ly, endpoint=True),
                              var_x_plot, 10, vmin=var_min, vmax=var_max)
            plt.scatter(xv, yv, marker='+', facecolors='dimgrey')
            plt.plot([x_min, x_min, x_max, x_max, x_min], [y_min, y_max, y_max, y_min, y_min], "k")
            plt.plot(trajectory_1[:, 0], trajectory_1[:, 1], color='green')
            for jj in range(0, n_k):  # Iterate over all trajectories
                plt.plot(tau_x[0, :, jj], tau_x[1, :, jj], color='black')
            plt.plot(x_auv[0], x_auv[1], marker='o', markerfacecolor='none')
            plt.plot(tau_optimal[0, :], tau_optimal[1, :], color='blue')

        else:
            """Plot GMRF mean"""
            ax1 = fig1.add_subplot(222)
            c1 = ax1.contourf(np.linspace(x_min, x_max, num=lxf, endpoint=True),
                              np.linspace(y_min, y_max, num=lyf, endpoint=True),
                              mue_x_plot[dvy:(lyf + dvy), dvx:(lxf + dvx)], vmin=vmin, vmax=vmax, levels=levels)
            # plt.scatter(xv[dvy:(lyf+dvy), dvx:(lxf+dvx)], yv[dvy:(lyf+dvy), dvx:(lxf+dvx)], marker='+', facecolors='dimgrey')
            plt.plot(x_auv[0], x_auv[1], marker='o', markerfacecolor='none')

            """Plot GMRF variance"""
            ax2 = fig1.add_subplot(223)
            c2 = ax2.contourf(np.linspace(x_min, x_max, num=lxf, endpoint=True),
                              np.linspace(y_min, y_max, num=lyf, endpoint=True),
                              var_x_plot[dvy:(lyf + dvy), dvx:(lxf + dvx)], 10, vmin=var_min, vmax=var_max)
            # plt.scatter(xv[dvy:(lyf+dvy), dvx:(lxf+dvx)], yv[dvy:(lyf+dvy), dvx:(lxf+dvx)], marker='+', facecolors='dimgrey')
            plt.plot(trajectory_1[:, 0], trajectory_1[:, 1], color='green')
            for jj in range(0, n_k):  # Iterate over all trajectories
                plt.plot(tau_x[0, :, jj], tau_x[1, :, jj], color='black')
            plt.plot(x_auv[0], x_auv[1], marker='o', markerfacecolor='none')
            plt.plot(tau_optimal[0, :], tau_optimal[1, :], color='blue')

        """Plot Hyperparameter estimate"""
        ax3 = fig1.add_subplot(224, projection='3d')
        # colors = plt.cm.jet(pi_theta.flatten() / float(pi_theta.max()))  # Color height dependent
        ax3.bar3d(x, y, bottom, 1, 1, pi_theta, color=colors, alpha=0.5)

        fig1.canvas.draw_idle()
        plt.pause(0.5)
        plt.clf()
        # plt.waitforbuttonpress()
