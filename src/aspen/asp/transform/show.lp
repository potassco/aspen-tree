#show.
#show aspen(X) :
  aspen(X),
  X=(replace(N,T);
     append(N,T);
     prepend(N,T);
     comes_before(E1,E2);
     next_program(P,C);
     log(L,T);
     log(N,L,T);
     print(T);
     print(O,T);
     exception(T);
     exception(N,T);
     return(path_of_node(N),P)).
