# MiniLang Grammar (EBNF)

MiniLang is a small, statically typed imperative language with `int` and `bool`.
Terminals are in quotes or UPPERCASE (token classes); `{ x }` = zero or more,
`[ x ]` = optional, `|` = alternative.

```ebnf
program     = { function } EOF ;

function    = "func" ID "(" [ params ] ")" ":" type block ;
params      = param { "," param } ;
param       = ID ":" type ;
type        = "int" | "bool" ;

block       = "{" { statement } "}" ;

statement   = let_stmt | assign_stmt | if_stmt | while_stmt
            | return_stmt | print_stmt | block | expr_stmt ;

let_stmt    = "let" ID ":" type "=" expr ";" ;
assign_stmt = ID "=" expr ";" ;
if_stmt     = "if" "(" expr ")" block [ "else" ( if_stmt | block ) ] ;
while_stmt  = "while" "(" expr ")" block ;
return_stmt = "return" [ expr ] ";" ;
print_stmt  = "print" "(" expr ")" ";" ;
expr_stmt   = expr ";" ;

(* expressions, lowest to highest precedence; all binary ops are left-assoc *)
expr        = or_expr ;
or_expr     = and_expr  { "||" and_expr } ;
and_expr    = eq_expr   { "&&" eq_expr } ;
eq_expr     = rel_expr  { ( "==" | "!=" ) rel_expr } ;
rel_expr    = add_expr  { ( "<" | ">" | "<=" | ">=" ) add_expr } ;
add_expr    = mul_expr  { ( "+" | "-" ) mul_expr } ;
mul_expr    = unary     { ( "*" | "/" | "%" ) unary } ;
unary       = ( "-" | "!" ) unary | primary ;
primary     = INT_LIT | "true" | "false"
            | ID [ "(" [ args ] ")" ]
            | "(" expr ")" ;
args        = expr { "," expr } ;
```

## Lexical rules

| Token class | Pattern |
|---|---|
| `ID` | `[A-Za-z_][A-Za-z0-9_]*` (not a keyword) |
| `INT_LIT` | `[0-9]+` (a digit run followed directly by a letter is an error) |
| Keywords | `func let if else while return print int bool true false` |
| Operators | `+ - * / % == != < > <= >= && \|\| ! =` |
| Delimiters | `( ) { } , ; :` |
| Comments | `// to end of line`, `/* block */` (not nested) |
| Whitespace | space, tab, CR, LF (ignored) |

The lexer uses longest match (`<=` before `<`). A manual DFA is used: dispatch on
the first character, then consume the longest lexeme.

## Precedence table (high to low)

| Level | Operators | Assoc |
|---|---|---|
| 7 | unary `-` `!` | right |
| 6 | `*` `/` `%` | left |
| 5 | `+` `-` | left |
| 4 | `<` `>` `<=` `>=` | left |
| 3 | `==` `!=` | left |
| 2 | `&&` | left |
| 1 | `\|\|` | left |

## Parsing technique

Recursive descent with one method per precedence level. Left recursion is
removed by the standard transformation `A -> A op B | B` into
`A -> B { op B }`, implemented as a loop (this also gives left associativity).
The grammar is LL(1) except for statement starts beginning with `ID`
(`x = ...;` versus `f(x);`), which needs one extra token of lookahead (LL(2)).
`else if` is parsed as `else` followed by a nested `if`.

## Checks deferred to semantic analysis (Review 2)

The parser accepts these; the semantic analyzer will reject them:
`return;` with no value (every function returns a value), type mismatches,
undeclared names, duplicate declarations, wrong call arity/types, non-bool
conditions, missing `main`, and paths that do not return.
