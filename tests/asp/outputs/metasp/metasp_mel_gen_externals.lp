% intervals contain numbers, arithmetic terms and #sup, which are
% terms and must not occur in externals.
&next(&i(D,D+1),at(L')) :- at(L), go(L'), distance(L,L',D).
&next(&i(0,#sup),at(L)) :- at(L), not &final.
&next(push) :- &initial.
:- not &eventually(&i(0,size),goal), &initial.
#external &eventually(&i(0,size),goal).
#external &initial.
#external &initial.
#external push.
#external &final: at(L).
#external at(L): at(L).
#external at(L'): distance(L,L',D), go(L'), at(L).
