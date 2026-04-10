import pyfiglet

skull = """                     ____________
                      .~      ,   . ~.
                     /                \\
                    /      /~\\/~\\   ,  \\
                   |   .   \\    /   '   |
                   |         \\/         |
          XX       |  /~~\\        /~~\\  |       XX
        XX  X      | |  o  \\    /  o  | |      X  XX
      XX     X     |  \\____/    \\____/  |     X     XX
 XXXXX     XX      \\         /\\        ,/      XX     XXXXX
X        XX%;;@      \\      /  \\     ,/      @%%;XX        X
X       X  @%%;;@     |           '  |     @%%;;@  X       X
X      X     @%%;;@   |. ` ; ; ; ;  ,|   @%%;;@     X      X
 X    X        @%%;;@                  @%%;;@        X    X
  X   X          @%%;;@              @%%;;@          X   X
   X  X            @%%;;@          @%%;;@            X  X
    XX X             @%%;;@      @%%;;@             X XX
      XXX              @%%;;@  @%%;;@              XXX
                         @%%;;%%;;@
                           @%%;;@
                         @%%;;@..@@
                          @@@  @@@"""

logo = pyfiglet.figlet_format('FIELDKIT', font='doom')

width = max(max(len(l) for l in skull.split('\n')), max(len(l) for l in logo.split('\n')))

padded_skull = '\n'.join(l.ljust(width) for l in skull.split('\n'))
padded_logo = '\n'.join(l.center(width) for l in logo.split('\n'))

print(padded_skull)
print(padded_logo)
