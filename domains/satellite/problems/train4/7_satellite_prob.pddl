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
	instrument4 - instrument
	satellite4 - satellite
	instrument5 - instrument
	satellite5 - satellite
	instrument6 - instrument
	spectrograph2 - mode
	infrared0 - mode
	thermograph3 - mode
	image1 - mode
	spectrograph4 - mode
	groundstation0 - direction
	star2 - direction
	star4 - direction
	groundstation1 - direction
	groundstation3 - direction
	phenomenon5 - direction
	phenomenon6 - direction
	planet7 - direction
	phenomenon8 - direction
	planet9 - direction
	phenomenon10 - direction
	planet11 - direction
)
(:init
	(supports instrument0 spectrograph4)
	(supports instrument0 spectrograph2)
	(supports instrument0 infrared0)
	(calibration_target instrument0 star4)
	(on_board instrument0 satellite0)
	(power_avail satellite0)
	(pointing satellite0 groundstation0)
	(supports instrument1 infrared0)
	(supports instrument1 thermograph3)
	(calibration_target instrument1 groundstation1)
	(on_board instrument1 satellite1)
	(power_avail satellite1)
	(pointing satellite1 groundstation0)
	(supports instrument2 thermograph3)
	(supports instrument2 infrared0)
	(calibration_target instrument2 star4)
	(on_board instrument2 satellite2)
	(power_avail satellite2)
	(pointing satellite2 phenomenon5)
	(supports instrument3 spectrograph2)
	(calibration_target instrument3 star4)
	(supports instrument4 infrared0)
	(calibration_target instrument4 groundstation1)
	(on_board instrument3 satellite3)
	(on_board instrument4 satellite3)
	(power_avail satellite3)
	(pointing satellite3 groundstation1)
	(supports instrument5 thermograph3)
	(calibration_target instrument5 groundstation1)
	(on_board instrument5 satellite4)
	(power_avail satellite4)
	(pointing satellite4 groundstation0)
	(supports instrument6 image1)
	(calibration_target instrument6 groundstation3)
	(on_board instrument6 satellite5)
	(power_avail satellite5)
	(pointing satellite5 phenomenon10)
)
(:goal (and
	(pointing satellite2 star4)
	(have_image phenomenon5 image1)
	(have_image phenomenon6 spectrograph4)
	(have_image planet7 infrared0)
	(have_image phenomenon8 thermograph3)
	(have_image planet9 image1)
	(have_image phenomenon10 spectrograph2)
	(have_image planet11 image1)
))

)
