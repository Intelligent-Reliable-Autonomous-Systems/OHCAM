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
	thermograph1 - mode
	image0 - mode
	infrared3 - mode
	image2 - mode
	spectrograph4 - mode
	groundstation1 - direction
	star4 - direction
	star0 - direction
	groundstation3 - direction
	groundstation2 - direction
	star5 - direction
	planet6 - direction
	phenomenon7 - direction
	star8 - direction
	planet9 - direction
	planet10 - direction
	star11 - direction
)
(:init
	(supports instrument0 image0)
	(supports instrument0 infrared3)
	(calibration_target instrument0 groundstation2)
	(supports instrument1 image0)
	(supports instrument1 spectrograph4)
	(supports instrument1 infrared3)
	(calibration_target instrument1 groundstation1)
	(on_board instrument0 satellite0)
	(on_board instrument1 satellite0)
	(power_avail satellite0)
	(pointing satellite0 star0)
	(supports instrument2 thermograph1)
	(supports instrument2 infrared3)
	(calibration_target instrument2 star4)
	(on_board instrument2 satellite1)
	(power_avail satellite1)
	(pointing satellite1 star0)
	(supports instrument3 infrared3)
	(supports instrument3 image2)
	(calibration_target instrument3 groundstation2)
	(supports instrument4 image0)
	(calibration_target instrument4 groundstation3)
	(on_board instrument3 satellite2)
	(on_board instrument4 satellite2)
	(power_avail satellite2)
	(pointing satellite2 star11)
	(supports instrument5 infrared3)
	(calibration_target instrument5 star4)
	(on_board instrument5 satellite3)
	(power_avail satellite3)
	(pointing satellite3 star8)
	(supports instrument6 thermograph1)
	(supports instrument6 image2)
	(calibration_target instrument6 star0)
	(supports instrument7 spectrograph4)
	(supports instrument7 image0)
	(supports instrument7 image2)
	(calibration_target instrument7 groundstation3)
	(on_board instrument6 satellite4)
	(on_board instrument7 satellite4)
	(power_avail satellite4)
	(pointing satellite4 star0)
	(supports instrument8 image0)
	(supports instrument8 infrared3)
	(calibration_target instrument8 groundstation3)
	(supports instrument9 thermograph1)
	(supports instrument9 image0)
	(supports instrument9 infrared3)
	(calibration_target instrument9 groundstation2)
	(on_board instrument8 satellite5)
	(on_board instrument9 satellite5)
	(power_avail satellite5)
	(pointing satellite5 groundstation2)
)
(:goal (and
	(have_image star5 infrared3)
	(have_image planet6 image0)
	(have_image phenomenon7 image2)
	(have_image star8 infrared3)
	(have_image planet9 thermograph1)
	(have_image planet10 image2)
	(have_image star11 infrared3)
))

)
