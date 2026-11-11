(define (problem random-2x3-283)
(:domain paint-nurikabe)
(:objects n0 - num0
  pos-0-0 pos-0-1 pos-0-2 pos-1-0 pos-1-1 pos-1-2 - cell
  n1 n2 - num
  g0 - group
)
(:init
 (next n0 n1)
 (next n1 n2)

 (connected pos-0-0 pos-1-0)
 (connected pos-0-0 pos-0-1)
 (connected pos-0-1 pos-1-1)
 (connected pos-0-1 pos-0-2)
 (connected pos-0-1 pos-0-0)
 (connected pos-0-2 pos-1-2)
 (connected pos-0-2 pos-0-1)
 (connected pos-1-0 pos-1-1)
 (connected pos-1-0 pos-0-0)
 (connected pos-1-1 pos-1-2)
 (connected pos-1-1 pos-0-1)
 (connected pos-1-1 pos-1-0)
 (connected pos-1-2 pos-0-2)
 (connected pos-1-2 pos-1-1)

 (robot-pos pos-0-0)
 (moving)

 (source pos-1-1 g0)

 (available pos-0-0)
 (available pos-0-2)
 
 (part-of pos-1-2 g0)
 (part-of pos-0-1 g0)
 (part-of pos-1-0 g0)
 (remaining-cells g0 n2)
)
(:goal (and
 (group-painted g0)
))
)

