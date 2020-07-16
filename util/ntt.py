"""A module to multiply polynomials using the Fast Fourier Transform (FFT), Number Theoretic Transform (NTT),
and Fermat Theoretic Transform (FTT). See https://rijndael.ece.vt.edu/schaum/pdf/papers/2013hostb.pdf.
"""

from math import log, pi, cos, sin
import util.number_theory as nbtheory
from util.bit_operations import bit_reverse_vec, reverse_bits

class NTTContext:
    """An instance of Number/Fermat Theoretic Transform parameters.

    Here, R is the quotient ring Z_a[x]/f(x), where f(x) = x^d + 1.
    The NTTContext keeps track of the ring degree d, the coefficient
    modulus a, a root of unity w so that w^2d = 1 (mod a), and
    precomputations to perform the NTT/FTT and the inverse NTT/FTT.

    Attributes:
        coeff_modulus (int): Modulus for coefficients of the polynomial.
        degree (int): Degree of the polynomial ring.
        roots_of_unity (list): The ith member of the list is w^i, where w
            is a root of unity.
        roots_of_unity_inv (list): The ith member of the list is w^(-i),
            where w is a root of unity.
        scaled_rou_inv (list): The ith member of the list is 1/n * w^(-i),
            where w is a root of unity.
        reversed_bits (list): The ith member of the list is the bits of i
            reversed, used in the iterative implementation of NTT.
    """

    def __init__(self, poly_degree, coeff_modulus, root_of_unity=None):
        """Inits NTTContext with a coefficient modulus for the polynomial ring
        Z[x]/f(x) where f has the given poly_degree.

        Args:
            poly_degree (int): Degree of the polynomial ring.
            coeff_modulus (int): Modulus for coefficients of the polynomial.
            root_of_unity (int): Root of unity to perform the NTT with. If it
                takes its default value of None, we compute a root of unity to
                use.
        """
        assert (poly_degree & (poly_degree - 1)) == 0, \
            "Polynomial degree must be a power of 2. d = " + str(poly_degree) + " is not."
        self.coeff_modulus = coeff_modulus
        self.degree = poly_degree
        if not root_of_unity:
            # We use the (2d)-th root of unity, since d of these are roots of x^d + 1, which can be used
            # to uniquely identify any polynomial mod x^d + 1 from the CRT representation of x^d + 1.
            root_of_unity = nbtheory.root_of_unity(order=2 * poly_degree, modulus=coeff_modulus)

        self.precompute_ntt(root_of_unity)

    def precompute_ntt(self, root_of_unity):
        """Performs precomputations for the NTT and inverse NTT.

        Precomputes all powers of roots of unity for the NTT and scaled powers of inverse
        roots of unity for the inverse NTT.

        Args:
            root_of_unity (int): Root of unity to perform the NTT with.
        """

        # Find powers of root of unity.
        self.roots_of_unity = [1] * self.degree
        for i in range(1, self.degree):
            self.roots_of_unity[i] = (self.roots_of_unity[i - 1] * root_of_unity) % self.coeff_modulus

        # Find powers of inverse root of unity.
        root_of_unity_inv = nbtheory.mod_inv(root_of_unity, self.coeff_modulus)
        self.roots_of_unity_inv = [1] * self.degree
        for i in range(1, self.degree):
            self.roots_of_unity_inv[i] = (self.roots_of_unity_inv[i - 1] * root_of_unity_inv) % self.coeff_modulus

        # Scale powers of inverse root of unity by 1/d for the inverse FTT computation.
        poly_degree_inv = nbtheory.mod_inv(self.degree, self.coeff_modulus)
        self.scaled_rou_inv = [0] * self.degree
        for i in range(self.degree):
            self.scaled_rou_inv[i] = (poly_degree_inv * self.roots_of_unity_inv[i]) % self.coeff_modulus

        # Compute precomputed array of reversed bits for iterated NTT.
        self.reversed_bits = [0] * self.degree
        width = int(log(self.degree, 2))
        for i in range(self.degree):
            self.reversed_bits[i] = reverse_bits(i, width) % self.degree

    def ntt(self, coeffs, rou):
        """Runs NTT on the given coefficients.

        Runs iterated NTT with the given coefficients and roots of unity. See
        paper for pseudocode.

        Args:
            coeffs (list): List of coefficients to transform. Must be the
                length of the polynomial degree.
            rou (list): Powers of roots of unity to be used for transformation.
                For inverse NTT, this is the powers of the inverse root of unity.

        Returns:
            List of transformed coefficients.
        """
        num_coeffs = len(coeffs)
        assert len(rou) == num_coeffs, \
            "Length of the roots of unity is too small. Length is " + len(rou)

        result = [coeffs[self.reversed_bits[i]] for i in range(num_coeffs)]

        log_num_coeffs = int(log(num_coeffs, 2))

        for logm in range(1, log_num_coeffs + 1):
            for j in range(0, num_coeffs, (1 << logm)):
                for i in range(1 << (logm - 1)):
                    index_even = j + i
                    index_odd = j + i + (1 << (logm - 1))

                    rou_idx = (i << (1 + log_num_coeffs - logm))
                    omega_factor = (rou[rou_idx] * result[index_odd]) % self.coeff_modulus

                    butterfly_plus = (result[index_even] + omega_factor) % self.coeff_modulus
                    butterfly_minus = (result[index_even] - omega_factor) % self.coeff_modulus

                    result[index_even] = butterfly_plus
                    result[index_odd] = butterfly_minus

        return result

    def ftt_fwd(self, coeffs):
        """Runs forward FTT on the given coefficients.

        Runs forward FTT with the given coefficients and parameters in the context.

        Args:
            coeffs (list): List of coefficients to transform. Must be the
                length of the polynomial degree.

        Returns:
            List of transformed coefficients.
        """
        num_coeffs = len(coeffs)
        assert num_coeffs == self.degree, "ftt_fwd: input length does not match context degree"

        # We use the FTT input given in the FTT paper.
        ftt_input = [(int(coeffs[i]) * self.roots_of_unity[i]) % self.coeff_modulus
                     for i in range(num_coeffs)]

        return self.ntt(coeffs=ftt_input, rou=self.roots_of_unity)

    def ftt_inv(self, coeffs):
        """Runs inverse FTT on the given coefficients.

        Runs inverse FTT with the given coefficients and parameters in the context.

        Args:
            coeffs (list): List of coefficients to transform. Must be the
                length of the polynomial degree.

        Returns:
            List of inversely transformed coefficients.
        """
        num_coeffs = len(coeffs)
        assert num_coeffs == self.degree, "ntt_inv: input length does not match context degree"

        to_scale_down = self.ntt(coeffs=coeffs, rou=self.roots_of_unity_inv)

        # We scale down the FTT output given in the FTT paper.
        to_scale_down = [(int(to_scale_down[i]) * self.scaled_rou_inv[i]) % self.coeff_modulus
                         for i in range(num_coeffs)]

        return to_scale_down


class FFTContext:
    """An instance of Fast Fourier Transform (FFT) parameters.

    The FFTContext keeps track of the length of the vector and precomputations
    to perform FFT.

    Attributes:
        M (int): Length of the FFT vector.
        roots_of_unity (list): The ith member of the list is w^i, where w
            is a root of unity.
        rot_group (list): Used for EMB only. Value at index i is 5i (mod M)
            for 0 <= i < M / 4.
        reversed_bits (list): The ith member of the list is the bits of i
            reversed, used in the iterative implementation of FFT.
    """
    def __init__(self, M):
        """Inits FFTContext with a length for the FFT vector.

        Args:
            M (int): Length of the FFT vector.
        """
        self.M = M
        self.roots_of_unity = [complex(0, 0)] * (M + 1)
        for i in range(M + 1):
            angle = 2 * pi * i / M
            self.roots_of_unity[i] = complex(cos(angle), sin(angle))

        Nh = M // 4
        self.rot_group = [1] * Nh
        for i in range(1, Nh):
            self.rot_group[i] = (5 * self.rot_group[i - 1]) % M

        # Compute precomputed array of reversed bits for iterated FFT.
        self.reversed_bits = [0] * Nh
        width = int(log(Nh, 2))
        for i in range(Nh):
            self.reversed_bits[i] = reverse_bits(i, width) % Nh

    def fft(self, coeffs, rou):
        """Runs FFT on the given coefficients.

        Runs iterated FFT with the given coefficients and roots of unity. See
        paper for pseudocode.

        Args:
            coeffs (list): List of coefficients to transform. Must be the
                length of the polynomial degree.
            rou (list): Powers of roots of unity to be used for transformation.
                For inverse NTT, this is the powers of the inverse root of unity.

        Returns:
            List of transformed coefficients.
        """
        num_coeffs = len(coeffs)
        assert len(rou) == num_coeffs, \
            "Length of the roots of unity is too small. Length is " + len(rou)

        result = [coeffs[self.reversed_bits[i]] for i in range(num_coeffs)]

        log_num_coeffs = int(log(num_coeffs, 2))

        for logm in range(1, log_num_coeffs + 1):
            for j in range(0, num_coeffs, (1 << logm)):
                for i in range(1 << (logm - 1)):
                    index_even = j + i
                    index_odd = j + i + (1 << (logm - 1))

                    rou_idx = (i << (1 + log_num_coeffs - logm))
                    omega_factor = (rou[rou_idx] * result[index_odd])

                    butterfly_plus = (result[index_even] + omega_factor)
                    butterfly_minus = (result[index_even] - omega_factor)

                    result[index_even] = butterfly_plus
                    result[index_odd] = butterfly_minus

        return result

    def check_input(self, values):
        """Checks that the length of the input vector is the correct size.

        Throws an error if the length of the input vector is not 1/4 the size
        of the FFT vector.

        Args:
            values (list): Input vector of complex numbers.
        """
        assert len(values) == self.M / 4, "Input vector must have length equal to self.M = " \
            + str(self.M / 4) + " != " + str(len(values)) + " = len(values)"

    def fft_fwd(self, coeffs):
        """Runs forward FFT on the given values.

        Runs forward FFT with the given values and parameters in the context.

        Args:
            coeffs (list): List of complex numbers to transform.

        Returns:
            List of transformed coefficients.
        """
        num_coeffs = len(coeffs)
        
        result = [coeffs[self.reversed_bits[i]] for i in range(num_coeffs)]

        ell = 2
        while ell <= num_coeffs:
            MoverLen = self.M // ell;
            ellh = ell >> 1
            for i in range(0, num_coeffs, ell):
                for j in range(ellh):
                    idx = j * MoverLen
                    u = result[i + j]
                    v = result[i + j + ellh]
                    v *= self.roots_of_unity[idx]
                    result[i + j] = u + v
                    result[i + j + ellh] = u - v
            ell *= 2

        return result

    def fft_inv(self, coeffs):
        """Runs inverse FFT on the given values.

        Runs inverse FFT with the given values and parameters in the context.

        Args:
            coeffs (list): List of complex numbers to transform.

        Returns:
            List of transformed coefficients.
        """
        num_coeffs = len(coeffs)

        result = [coeffs[self.reversed_bits[i]] for i in range(num_coeffs)]

        ell = 2
        while ell <= num_coeffs:
            MoverLen = self.M // ell
            ellh = ell >> 1
            for i in range(0, num_coeffs, ell):
                for j in range(ellh):
                    idx = (ell - j) * MoverLen
                    u = result[i + j]
                    v = result[i + j + ellh]
                    v *= self.roots_of_unity[idx]
                    result[i + j] = u + v
                    result[i + j + ellh] = u - v
            ell *= 2

        for i in range(num_coeffs):
            result[i] /= num_coeffs

        return result

    def emb(self, coeffs):
        """Runs forward packed FFT on the given values.

        Runs forward packed FFT with the given values for spaced slots
        and parameters in the context.

        Args:
            coeffs (list): List of complex numbers to transform.

        Returns:
            List of transformed coefficients.
        """

        num_coeffs = len(coeffs)

        res = bit_reverse_vec(coeffs)

        l = 2
        while l <= num_coeffs:
            for i in range(0, num_coeffs, l):
                lh = l >> 1
                lq = l << 2
                gap = int(self.M / lq)
                for j in range(lh):
                    idx = ((self.rot_group[j] % lq)) * gap
                    u = res[i + j]
                    v = res[i + j + lh]
                    v *= self.roots_of_unity[idx]
                    res[i + j] = u + v
                    res[i + j + lh] = u - v
            l <<= 1

        return res

    def emb_inv(self, coeffs):
        """Runs inverse FFT on the given values.

        Runs inverse FFT with the given values for spaced slots
        and parameters in the context.

        Args:
            values (list): List of complex numbers to transform.

        Returns:
            List of transformed coefficients.
        """

        res = coeffs.copy()

        num_coeffs = len(coeffs)
        l = num_coeffs
        while l >= 1:
            for i in range(0, num_coeffs, l):
                lh = l >> 1
                lq = l << 2
                gap = int(self.M / lq)

                for j in range(lh):
                    idx = (lq - (self.rot_group[j] % lq)) * gap
                    u = res[i + j] + res[i + j + lh]
                    v = res[i + j] - res[i + j + lh]
                    v *= self.roots_of_unity[idx]

                    res[i + j] = u
                    res[i + j + lh] = v

            l >>= 1

        to_scale_down = bit_reverse_vec(res)

        for i in range(num_coeffs):
            to_scale_down[i] /= num_coeffs

        return to_scale_down