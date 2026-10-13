% numbers are terms, even when given as constants in safe positions.
&range(1,4,a).
q :- &range(1,k,b), p.
#external a.
#external &range(1,k,b): p, b.
