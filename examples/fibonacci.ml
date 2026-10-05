func fib(n: int): int {
    let a: int = 0;
    let b: int = 1;
    let i: int = 0;
    while (i < n) {
        let t: int = a + b;
        a = b;
        b = t;
        i = i + 1;
    }
    return a;
}

func main(): int {
    print(fib(10));
    return 0;
}
