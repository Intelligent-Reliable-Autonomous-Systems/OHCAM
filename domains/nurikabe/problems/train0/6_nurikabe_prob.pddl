(define (problem random-3x3-18)
(:domain paint-nurikabe)
(:objects n0 - num0
  pos-0-0 pos-0-1 pos-0-2 pos-1-0 pos-1-1 pos-1-2 pos-2-0 pos-2-1 pos-2-2 - cell
  n1 n2 - num
  g0 g1 - group
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
 (connected pos-1-0 pos-2-0)
 (connected pos-1-0 pos-1-1)
 (connected pos-1-0 pos-0-0)
 (connected pos-1-1 pos-2-1)
 (connected pos-1-1 pos-1-2)
 (connected pos-1-1 pos-0-1)
 (connected pos-1-1 pos-1-0)
 (connected pos-1-2 pos-2-2)
 (connected pos-1-2 pos-0-2)
 (connected pos-1-2 pos-1-1)
 (connected pos-2-0 pos-2-1)
 (connected pos-2-0 pos-1-0)
 (connected pos-2-1 pos-2-2)
 (connected pos-2-1 pos-1-1)
 (connected pos-2-1 pos-2-0)
 (connected pos-2-2 pos-1-2)
 (connected pos-2-2 pos-2-1)

 (robot-pos pos-0-0)
 (moving)

 (source pos-1-0 g0)
 (source pos-1-2 g1)

 (available pos-0-1)
 (available pos-2-1)
 (blocked pos-1-1)
 (part-of pos-2-0 g0)
 (part-of pos-0-0 g0)
 (part-of pos-2-2 g1)
 (part-of pos-0-2 g1)
 (remaining-cells g0 n2)
 (remaining-cells g1 n1)
)
(:goal (and
 (group-painted g0)
 (group-painted g1)
))
)

