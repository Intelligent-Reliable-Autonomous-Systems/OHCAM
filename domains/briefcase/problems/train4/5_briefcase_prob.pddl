


(define (problem briefcase-o7)
(:domain briefcase)
(:objects l0 l1 l2 l3 l4 l5 l6 l7 - location
          o0 o1 o2 o3 o4 o5 o6 - portable)
(:init
(at o0 l0)
(at o1 l7)
(at o2 l1)
(at o3 l4)
(at o4 l3)
(at o5 l1)
(at o6 l6)
(is-at l6)
)
(:goal
(and
(at o0 l7)
(at o1 l1)
(at o2 l0)
(at o3 l3)
(at o4 l7)
(at o5 l0)
(at o6 l3)
(is-at l4)
)
)
)


