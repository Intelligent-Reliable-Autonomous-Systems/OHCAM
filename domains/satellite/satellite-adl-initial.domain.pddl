
(define (domain satellite)
  (:requirements :equality :typing :conditional-effects :negative-preconditions)
  (:types satellite direction instrument mode)
 (:predicates
               (on_board ?i - instrument ?s - satellite)
	       (supports ?i - instrument ?m - mode)
	       (pointing ?s - satellite ?d - direction)
	       (power_avail ?s - satellite)
	       (power_on ?i - instrument)
	       (calibrated ?i - instrument)
	       (have_image ?d - direction ?m - mode)
	       (calibration_target ?i - instrument ?d - direction))



  (:action turn_to
   :parameters (?s - satellite ?d_new - direction ?d_prev - direction)
   :precondition (and
   )
   :effect (and
   )
  )


  (:action switch_on
   :parameters (?i - instrument ?s - satellite)

   :precondition (and
   )
   :effect (and
   )

  )


  (:action switch_off
   :parameters (?i - instrument ?s - satellite)

   :precondition (and
   )
   :effect (and
   )
  )

  (:action calibrate
   :parameters (?s - satellite ?i - instrument ?d - direction)
   :precondition (and (on_board ?i ?s)
		      (calibration_target ?i ?d)
     )
   :effect (and
   )
  )


  (:action take_image
   :parameters (?s - satellite ?d - direction ?i - instrument ?m - mode)
   :precondition (and (calibrated ?i)
                      (on_board ?i ?s)
                      (supports ?i ?m)
     )
   :effect (and
   )
  )
)
