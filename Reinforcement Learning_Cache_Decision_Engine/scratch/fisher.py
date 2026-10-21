from scipy.stats import fisher_exact
print("Fisher exact, H5 2/5 vs H5v 4/5 seeds >= 300:", fisher_exact([[2, 3], [4, 1]])[1])
