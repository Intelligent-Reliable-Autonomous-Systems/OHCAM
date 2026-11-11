


(define (problem briefcase-o6)
(:domain briefcase)
(:objects l0 l1 l2 l3 l4 l5 l6 - location
          o0 o1 o2 o3 o4 o5 - portable)
(:init
(at o0 l5)
(at o1 l3)
(at o2 l5)
(at o3 l3)
(at o4 l6)
(at o5 l2)
(is-at l0)
)
(:goal
(and
(at o0 l1)
(at o1 l1)
(at o2 l5)
(at o3 l4)
(at o4 l4)
(at o5 l3)
(is-at l3)
)
)
)


