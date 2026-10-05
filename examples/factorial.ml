// Recursive factorial
func fact(n: int): int {
    if (n <= 1) { return 1; }
    return n * fact(n - 1);
}

func main(): int {
    print(fact(5));
    return 0;
}
