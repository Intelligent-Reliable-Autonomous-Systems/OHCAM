(define (domain briefcase)
(:requirements :typing :negative-preconditions :conditional-effects)
(:types portable location)
(:predicates (at ?x - portable ?y - location)
             (in ?x - portable)
             (is-at ?y - location))


(:action move
  :parameters (?m ?l - location)
  :precondition  (and )
  :effect (and )
)

  (:action take-out
      :parameters (?x - portable)
      :precondition (and )
      :effect (and )
  )

  (:action put-in
      :parameters (?x - portable ?l - location)
      :precondition (and )
      :effect (and )
      )
)