import os
import sys
import time
import pyfiglet

def boot():
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

    logo = pyfiglet.figlet_format("FIELDKIT", font="doom")
    width = max(
        max(len(l) for l in skull.split("\n")),
        max(len(l) for l in logo.split("\n"))
    )
    padded_skull = "\n".join(l.ljust(width) for l in skull.split("\n"))
    padded_logo = "\n".join(l.center(width) for l in logo.split("\n"))
    full = padded_skull + "\n" + padded_logo

    with open("/tmp/fieldkit_logo.txt", "w") as f:
        f.write(full)

    os.system("cat /tmp/fieldkit_logo.txt | tte --frame-rate 60 decrypt")

    lines = [
        ("INITIALISING SYSTEMS...", "print", 120),
        ("GPS ACQUIRING...", "print", 120),
        ("SDR CALIBRATING...", "print", 120),
        ("LORA HANDSHAKE...", "print", 120),
        ("DRONE DETECTION ONLINE...", "print", 120),
        ("SYSTEMS ONLINE", "beams", 100),
    ]

    for text, effect, rate in lines:
        os.system(f'echo "{text}" | tte --frame-rate {rate} {effect}')
        time.sleep(0.1)

    time.sleep(0.3)

def login():
    os.system("clear")
    print("\n\n")
    print("  " + "═" * 40)
    print("  FIELDKIT OS v1.0  --  ACCESS CONTROL")
    print("  " + "═" * 40)
    print()
    attempts = 0
    while attempts < 3:
        user = input("  USER: ")
        import getpass
        pwd = getpass.getpass("  PASS: ")
        if user == "field" and pwd == "kit":
            print()
            print("  ACCESS GRANTED")
            time.sleep(0.5)
            os.system('echo "LOADING FIELDKIT..." | tte --frame-rate 100 beams')
            time.sleep(0.3)
            return True
        else:
            attempts += 1
            remaining = 3 - attempts
            print(f"  ACCESS DENIED  --  {remaining} attempts remaining\n")
    print("  LOCKOUT INITIATED")
    sys.exit(1)

if __name__ == "__main__":
    boot()
    login()
    from fieldkit import FieldKit
    app = FieldKit()
    app.run()
