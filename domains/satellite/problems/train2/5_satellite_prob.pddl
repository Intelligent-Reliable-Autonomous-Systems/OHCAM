(define (problem strips-sat-x-1)
(:domain satellite)
(:objects
	satellite0 - satellite
	instrument0 - instrument
	satellite1 - satellite
	instrument1 - instrument
	satellite2 - satellite
	instrument2 - instrument
	satellite3 - satellite
	instrument3 - instrument
	satellite4 - satellite
	instrument4 - instrument
	infrared1 - mode
	thermograph3 - mode
	thermograph2 - mode
	image0 - mode
	groundstation2 - direction
	star1 - direction
	groundstation3 - direction
	groundstation0 - direction
	phenomenon4 - direction
	planet5 - direction
	planet6 - direction
	planet7 - direction
	planet8 - direction
	planet9 - direction
)
(:init
	(supports instrument0 infrared1)
	(supports instrument0 thermograph2)
	(supports instrument0 image0)
	(calibration_target instrument0 star1)
	(on_board instrument0 satellite0)
	(power_avail satellite0)
	(pointing satellite0 planet5)
	(supports instrument1 image0)
	(supports instrument1 thermograph2)
	(calibration_target instrument1 groundstation0)
	(on_board instrument1 satellite1)
	(power_avail satellite1)
	(pointing satellite1 phenomenon4)
	(supports instrument2 thermograph2)
	(calibration_target instrument2 groundstation3)
	(on_board instrument2 satellite2)
	(power_avail satellite2)
	(pointing satellite2 star1)
	(supports instrument3 image0)
	(supports instrument3 infrared1)
	(supports instrument3 thermograph3)
	(calibration_target instrument3 groundstation3)
	(on_board instrument3 satellite3)
	(power_avail satellite3)
	(pointing satellite3 star1)
	(supports instrument4 infrared1)
	(calibration_target instrument4 groundstation0)
	(on_board instrument4 satellite4)
	(power_avail satellite4)
	(pointing satellite4 planet7)
)
(:goal (and
	(pointing satellite0 groundstation3)
	(pointing satellite1 groundstation2)
	(pointing satellite2 groundstation3)
	(have_image phenomenon4 thermograph2)
	(have_image planet5 thermograph2)
	(have_image planet6 image0)
	(have_image planet7 image0)
	(have_image planet8 thermograph3)
	(have_image planet9 image0)
))

)
