(define (problem strips-sat-x-1)
(:domain satellite)
(:objects
	satellite0 - satellite
	instrument0 - instrument
	instrument1 - instrument
	satellite1 - satellite
	instrument2 - instrument
	instrument3 - instrument
	satellite2 - satellite
	instrument4 - instrument
	satellite3 - satellite
	instrument5 - instrument
	instrument6 - instrument
	satellite4 - satellite
	instrument7 - instrument
	satellite5 - satellite
	instrument8 - instrument
	instrument9 - instrument
	thermograph1 - mode
	infrared0 - mode
	infrared3 - mode
	image2 - mode
	star0 - direction
	star4 - direction
	star1 - direction
	star2 - direction
	groundstation3 - direction
	star5 - direction
	phenomenon6 - direction
	star7 - direction
	star8 - direction
	phenomenon9 - direction
	phenomenon10 - direction
	star11 - direction
)
(:init
	(supports instrument0 thermograph1)
	(supports instrument0 image2)
	(calibration_target instrument0 star2)
	(supports instrument1 image2)
	(calibration_target instrument1 groundstation3)
	(on_board instrument0 satellite0)
	(on_board instrument1 satellite0)
	(power_avail satellite0)
	(pointing satellite0 star5)
	(supports instrument2 image2)
	(calibration_target instrument2 star4)
	(supports instrument3 image2)
	(supports instrument3 infrared0)
	(calibration_target instrument3 groundstation3)
	(on_board instrument2 satellite1)
	(on_board instrument3 satellite1)
	(power_avail satellite1)
	(pointing satellite1 phenomenon9)
	(supports instrument4 thermograph1)
	(supports instrument4 image2)
	(calibration_target instrument4 groundstation3)
	(on_board instrument4 satellite2)
	(power_avail satellite2)
	(pointing satellite2 phenomenon6)
	(supports instrument5 infrared3)
	(calibration_target instrument5 star4)
	(supports instrument6 thermograph1)
	(supports instrument6 infrared0)
	(calibration_target instrument6 star1)
	(on_board instrument5 satellite3)
	(on_board instrument6 satellite3)
	(power_avail satellite3)
	(pointing satellite3 star8)
	(supports instrument7 infrared3)
	(calibration_target instrument7 star2)
	(on_board instrument7 satellite4)
	(power_avail satellite4)
	(pointing satellite4 star4)
	(supports instrument8 image2)
	(supports instrument8 infrared3)
	(supports instrument8 thermograph1)
	(calibration_target instrument8 groundstation3)
	(supports instrument9 thermograph1)
	(supports instrument9 image2)
	(calibration_target instrument9 groundstation3)
	(on_board instrument8 satellite5)
	(on_board instrument9 satellite5)
	(power_avail satellite5)
	(pointing satellite5 phenomenon6)
)
(:goal (and
	(pointing satellite3 groundstation3)
	(pointing satellite5 phenomenon9)
	(have_image star5 infrared0)
	(have_image phenomenon6 infrared3)
	(have_image star7 infrared0)
	(have_image star8 infrared0)
	(have_image phenomenon9 image2)
	(have_image phenomenon10 infrared0)
	(have_image star11 image2)
))

)
