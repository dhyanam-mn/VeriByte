func is_prime(n: int): bool {
    if (n < 2) { return false; }
    let d: int = 2;
    while (d * d <= n) {
        if (n % d == 0) { return false; }
        d = d + 1;
    }
    return true;
}

func main(): int {
    let k: int = 2;
    while (k < 30) {
        if (is_prime(k)) { print(k); }
        k = k + 1;
    }
    return 0;
}
