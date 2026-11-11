(define (problem strips-sat-x-1)
(:domain satellite)
(:objects
	satellite0 - satellite
	instrument0 - instrument
	instrument1 - instrument
	satellite1 - satellite
	instrument2 - instrument
	satellite2 - satellite
	instrument3 - instrument
	instrument4 - instrument
	satellite3 - satellite
	instrument5 - instrument
	satellite4 - satellite
	instrument6 - instrument
	instrument7 - instrument
	satellite5 - satellite
	instrument8 - instrument
	instrument9 - instrument
	spectrograph1 - mode
	infrared3 - mode
	image0 - mode
	image4 - mode
	thermograph2 - mode
	groundstation2 - direction
	star4 - direction
	groundstation1 - direction
	star3 - direction
	groundstation0 - direction
	star5 - direction
	star6 - direction
	star7 - direction
	planet8 - direction
	star9 - direction
	planet10 - direction
	star11 - direction
)
(:init
	(supports instrument0 spectrograph1)
	(calibration_target instrument0 groundstation2)
	(supports instrument1 thermograph2)
	(calibration_target instrument1 groundstation0)
	(on_board instrument0 satellite0)
	(on_board instrument1 satellite0)
	(power_avail satellite0)
	(pointing satellite0 star7)
	(supports instrument2 thermograph2)
	(supports instrument2 image0)
	(supports instrument2 image4)
	(calibration_target instrument2 groundstation1)
	(on_board instrument2 satellite1)
	(power_avail satellite1)
	(pointing satellite1 planet8)
	(supports instrument3 image4)
	(supports instrument3 image0)
	(calibration_target instrument3 star3)
	(supports instrument4 thermograph2)
	(supports instrument4 image4)
	(calibration_target instrument4 star4)
	(on_board instrument3 satellite2)
	(on_board instrument4 satellite2)
	(power_avail satellite2)
	(pointing satellite2 star9)
	(supports instrument5 thermograph2)
	(calibration_target instrument5 groundstation0)
	(on_board instrument5 satellite3)
	(power_avail satellite3)
	(pointing satellite3 groundstation0)
	(supports instrument6 image0)
	(calibration_target instrument6 groundstation1)
	(supports instrument7 thermograph2)
	(supports instrument7 infrared3)
	(supports instrument7 image0)
	(calibration_target instrument7 star3)
	(on_board instrument6 satellite4)
	(on_board instrument7 satellite4)
	(power_avail satellite4)
	(pointing satellite4 star11)
	(supports instrument8 spectrograph1)
	(supports instrument8 infrared3)
	(calibration_target instrument8 groundstation0)
	(supports instrument9 image4)
	(supports instrument9 thermograph2)
	(supports instrument9 image0)
	(calibration_target instrument9 groundstation0)
	(on_board instrument8 satellite5)
	(on_board instrument9 satellite5)
	(power_avail satellite5)
	(pointing satellite5 groundstation1)
)
(:goal (and
	(pointing satellite1 star3)
	(have_image star5 image4)
	(have_image star6 image0)
	(have_image star7 image4)
	(have_image planet8 image4)
	(have_image star9 image4)
	(have_image planet10 image4)
	(have_image star11 image4)
))

)
