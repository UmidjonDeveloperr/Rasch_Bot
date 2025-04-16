import warnings
import numpy as np
import pandas as pd
from numba import njit
from scipy.optimize import minimize

warnings.filterwarnings('ignore')


class FastRaschModel:
    def __init__(self):
        self.item_difficulty = None
        self.person_ability = None

    @staticmethod
    @njit
    def _calculate_log_likelihood(X, beta, theta):
        log_lik = 0.0
        n_persons, n_items = X.shape
        for i in range(n_persons):
            for j in range(n_items):
                diff = theta[i] - beta[j]
                if diff > 20:
                    p = 1.0
                elif diff < -20:
                    p = 0.0
                else:
                    p = 1.0 / (1.0 + np.exp(-diff))

                if X[i, j] == 1:
                    log_lik += np.log(p)
                else:
                    log_lik += np.log(1.0 - p)
        return -log_lik

    def fit(self, X, max_iter=50, tol=1e-3, batch_size=2000):
        X_np = X.values if isinstance(X, pd.DataFrame) else X
        n_persons, n_items = X_np.shape

        # if np.all((X_np == X_np[0]).all(axis=1)):
        #     self.item_difficulty = 0
        #     self.person_ability = 0
        #     return

        initial_beta = np.zeros(n_items)
        initial_theta = np.zeros(n_persons)
        initial_guess = np.concatenate([initial_beta, initial_theta])

        bounds = [(-5, 5)] * n_items + [(-5, 5)] * n_persons

        if n_persons > batch_size:
            for iteration in range(max_iter):
                batch_idx = np.random.choice(n_persons, size=batch_size, replace=False)
                X_batch = X_np[batch_idx, :]

                def batch_neg_log_lik(params):
                    beta = params[:n_items]
                    theta = params[n_items:]
                    theta_batch = theta[batch_idx]
                    return self._calculate_log_likelihood(X_batch, beta, theta_batch)

                result = minimize(batch_neg_log_lik, initial_guess,
                                  method='L-BFGS-B',
                                  bounds=bounds,
                                  options={'maxiter': 10, 'gtol': tol})

                initial_guess = result.x
                if result.fun < tol:
                    break
        else:
            def full_neg_log_lik(params):
                beta = params[:n_items]
                theta = params[n_items:]
                return self._calculate_log_likelihood(X_np, beta, theta)

            result = minimize(full_neg_log_lik, initial_guess,
                              method='L-BFGS-B',
                              bounds=bounds,
                              options={'maxiter': max_iter, 'gtol': tol})

        self.item_difficulty = result.x[:n_items]
        self.person_ability = result.x[n_items:]
