# hermes-runtime

AGK OS sources compile deterministically into Hermes Profile Distributions for Director and worker profiles. Bootstrap pins the reviewed Hermes release commit in a shared executable directory; every Zone retains an independent `HERMES_HOME`. Live profile, gateway and fresh-session acceptance still require enrollment and readback.
