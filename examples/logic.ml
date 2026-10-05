func in_range(x: int, lo: int, hi: int): bool {
    return x >= lo && x <= hi || !(x != 0);
}

func main(): int {
    if (in_range(5, 1, 10)) { print(1); } else if (true) { print(2); } else { print(3); }
    return -(1 + 2) * 3;
}
