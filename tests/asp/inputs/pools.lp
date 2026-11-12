% Pools in every position allowed by the clingo grammar, including
% nested and empty pool items.
#theory t { term { }; &a/0 : term, any; &b/1 : term, any }.

% statements
p(1;2).
-p(1;2).
:- p(1;2).
a :- p(b;c), q(e;f).
a :- X<(1;2), q(X).
a :- X!=|1;-2|, q(X).
p(1;2) :- not q(3;4), not not r(5;6).
a | b(1;2) :- c.
a :- (1;2) < #count{ X : p(X) }.
#show f(1;2) : p(3;4).
#external p(1;2) : q(3;4).
:~ p(1;2). [1@(2;3), (4;5)]
#heuristic p(1;2) : q(3;4). [1,true]
#project p(1;2) : q(3;4).
#edge ((1;2),3) : p(4;5).
#program p(k). a(1;2). % comment
#program base. b(3;4).

% conditional literals
a :- p(X;Y) : q.
a :- p(X) : q(X;Y).
a :- p : q(1;2), r(3;4).
a :- p(1;2) : q(3;4).
p : q(1;2) :- r(5;6).
p(1;2) : q(3;4) :- r.
p(1;2), q(3;4) : r(5;6) :- s.
a :- p(X) : q(X;Y), r(Y;Z); s((;1)).

% aggregate, optimize and theory elements
a :- { p(1;2) : q(3;4) }.
a :- #sum{ (1;2),X : p(X;Y) }.
{ p(1;2) : q(3;4) } :- r(5;6).
{ p(1;2) : q(3;4); r(f(1;2);3) } :- r(5;6).
#count{ X : p(X;Y) } :- r.
#count{ X : p(X;Y) : q(1;2) } :- r(|1;-2|).
#minimize{ 1,(2;3) : p(4;5); 6 : q(@g(7;)) }.
&a { 3 : p(5;6) }.
&a { 3 : p(5;6), q(7;8) }.
&b(1;2) { 3 : p }.
a :- &b(1;(2;3)) { 3 : p(4;5) }, x(-(1;2)).
p(1;2), q(3;4) : r(5;(6;7)) :- s(8;9), #sum{ (1;2),X : p(X;Y), t(1;2) } < (3;4).

% terms
p(f(1;2)).
p(|1;2|).
p(@f(1;2)).
p(1..(2;3)).
p(-(1;2)).
p(a,b;c;).
p((a;b),(c;d)).

% nested pools
p((1;2);3).
p(f((1;2);3)).
p((1;(2;3))).
p(f(g(1;2);3)).
p(f(1;(2;3)),(4;g(5;6))).

% empty pool items
p(1;).
p(;1;).
p(;).
p(@f(1;)).
p((1;)).
p((;1)).
p((1;;2)).
p((;;)).
p((1,;2)).
p((,;2)).
