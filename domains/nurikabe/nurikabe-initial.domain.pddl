(define (domain paint-nurikabe)
  (:requirements :typing :adl)
  (:types cell num group - object
      num0 - num)
  (:predicates
    (next ?n1 - num ?n2 - num)
    (connected ?c - cell ?c2 - cell)          ; Defines the graph structure
    (source ?x - cell ?g - group)             ; The initial position from which the robot must start painting
    (painted ?r - cell)                       ; Whether a tile has been painted
    (available ?x - cell)                     ; A cell does not belong to any group
    (part-of ?x - cell ?y - group)            ; Whether a cell "belongs to" a group. This happens when an adjacent cell belongs to such group
    (blocked ?x - cell)                       ; A cell belongs to two different groups so it cannot be painted of any color
    (remaining-cells ?x - group ?y - num)     ; How many tiles remain to be painted for every group
    (robot-pos ?x - cell)                     ; Position of the robot
    (moving)                                  ; The robot is currently not painting
    (painting ?g - group)                     ; The robot is currently painting a group
    (group-painted ?g - group)                ; The robot has painted a group
  )

  (:action move
    :parameters (?from - cell ?to - cell)
    :precondition (and
        (connected ?from ?to)
        (moving)
    )
    :effect (and
    )
  )

  (:action start-painting
    :parameters (?c - cell ?g - group ?n1 - num ?n2 - num)
    :precondition (and
        (source ?c ?g)
        (remaining-cells ?g ?n1)
    )
    :effect (and
    )
  )

  (:action move-painting
    :parameters (?from - cell ?to - cell ?g - group ?n1 - num ?n2 - num)
    :precondition (and
        (next ?n2 ?n1)
        (remaining-cells ?g ?n1)
        (robot-pos ?from)
    )
    :effect (and
    )
  )

  (:action end-painting
    :parameters (?g - group ?n0 - num0)
    :precondition (and
    )
    :effect (and
    )
  )
)
