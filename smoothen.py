'''Function to smooth some data, such as the reverse-engineered IAC that Mileva computed.

Followed this https://stackoverflow.com/questions/20618804/how-to-smooth-a-curve-for-a-dataset

May 30, 2024

'''
import datetime
import csv
import numpy as np

# From https://scipy.github.io/old-wiki/pages/Cookbook/SavitzkyGolay

def savitzky_golay(y, window_size, order, deriv=0, rate=1):
    r"""Smooth (and optionally differentiate) data with a Savitzky-Golay filter.
    The Savitzky-Golay filter removes high frequency noise from data.
    It has the advantage of preserving the original shape and
    features of the signal better than other types of filtering
    approaches, such as moving averages techniques.
    Parameters
    ----------
    y : array_like, shape (N,)
        the values of the time history of the signal.
    window_size : int
        the length of the window. Must be an odd integer number.
    order : int
        the order of the polynomial used in the filtering.
        Must be less then `window_size` - 1.
    deriv: int
        the order of the derivative to compute (default = 0 means only smoothing)
    Returns
    -------
    ys : ndarray, shape (N)
        the smoothed signal (or it's n-th derivative).
    Notes
    -----
    The Savitzky-Golay is a type of low-pass filter, particularly
    suited for smoothing noisy data. The main idea behind this
    approach is to make for each point a least-square fit with a
    polynomial of high order over a odd-sized window centered at
    the point.
    Examples
    --------
    t = np.linspace(-4, 4, 500)
    y = np.exp( -t**2 ) + np.random.normal(0, 0.05, t.shape)
    ysg = savitzky_golay(y, window_size=31, order=4)
    import matplotlib.pyplot as plt
    plt.plot(t, y, label='Noisy signal')
    plt.plot(t, np.exp(-t**2), 'k', lw=1.5, label='Original signal')
    plt.plot(t, ysg, 'r', label='Filtered signal')
    plt.legend()
    plt.show()
    References
    ----------
    .. [1] A. Savitzky, M. J. E. Golay, Smoothing and Differentiation of
       Data by Simplified Least Squares Procedures. Analytical
       Chemistry, 1964, 36 (8), pp 1627-1639.
    .. [2] Numerical Recipes 3rd Edition: The Art of Scientific Computing
       W.H. Press, S.A. Teukolsky, W.T. Vetterling, B.P. Flannery
       Cambridge University Press ISBN-13: 9780521880688
    """
    import numpy as np
    from math import factorial
    
    try:
        window_size = np.abs(np.int(window_size))
        order = np.abs(np.int(order))
    except ValueError as msg:
        raise ValueError("window_size and order have to be of type int")
    if window_size % 2 != 1 or window_size < 1:
        raise TypeError("window_size size must be a positive odd number")
    if window_size < order + 2:
        raise TypeError("window_size is too small for the polynomials order")
    order_range = range(order+1)
    half_window = (window_size -1) // 2
    # precompute coefficients
    b = np.mat([[k**i for i in order_range] for k in range(-half_window, half_window+1)])
    m = np.linalg.pinv(b).A[deriv] * rate**deriv * factorial(deriv)
    # pad the signal at the extremes with
    # values taken from the signal itself
    firstvals = y[0] - np.abs( y[1:half_window+1][::-1] - y[0] )
    lastvals = y[-1] + np.abs(y[-half_window-1:-1][::-1] - y[-1])
    y = np.concatenate((firstvals, y, lastvals))
    return np.convolve( m[::-1], y, mode='valid')

def read_curve_from_csv(filename):
    curve = []
    with open(filename, 'r') as fin:
        reader = csv.reader(fin)
        next(reader)            # skip the header row
        for row in reader:
            x = int(row[0])
            y = float(row[1])
            curve.append([x,y])
    return curve

def set_zero(seq, index):
    '''set to zero all sequence elements past (>=) given index. time 250 is index 50'''
    for i in range(index, len(seq)):
        seq[i] = 0

def normalize(seq):
    total = sum(seq)
    return [ v/total for v in seq ]

def today_str(fmt="%Y-%m-%d"):
    now = datetime.datetime.today()
    return now.strftime(fmt)


def main(win_size=17, degree=3, set_zero_index=50):
    iac = read_curve_from_csv('reverse_engineered_iac_2022-12-20.csv')
    iac_values = [ val[1] for val in iac ]
    iac_array = np.array(iac_values)
    set_zero(iac_array, set_zero_index)
    iac_smooth = savitzky_golay(iac_array, win_size, degree)
    set_zero(iac_smooth, set_zero_index)
    iac = normalize(iac_array)
    iac_smooth = normalize(iac_smooth)
    
    print(f"Time\tIAC\tSK_{win_size}_{degree}")
    for i in range(len(iac)):
        print(f"{i*5}\t{iac[i]}\t{iac_smooth[i]}")
    today = today_str()
    with open(f"iac_sk_{win_size}_{degree}_{today}.csv", "w") as fout:
        writer = csv.writer(fout)
        writer.writerow(['Time', 'IAC'])
        for i in range(len(iac)):
            writer.writerow([i*5, iac_smooth[i]])

if __name__ == '__main__':
    main()


        
