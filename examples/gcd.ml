func gcd(a: int, b: int): int {
    while (b != 0) {
        let t: int = b;
        b = a % b;
        a = t;
    }
    return a;
}

func main(): int {
    print(gcd(48, 18));
    return 0;
}
