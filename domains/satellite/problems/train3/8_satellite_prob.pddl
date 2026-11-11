(define (problem strips-sat-x-1)
(:domain satellite)
(:objects
	satellite0 - satellite
	instrument0 - instrument
	instrument1 - instrument
	instrument2 - instrument
	satellite1 - satellite
	instrument3 - instrument
	instrument4 - instrument
	instrument5 - instrument
	satellite2 - satellite
	instrument6 - instrument
	instrument7 - instrument
	satellite3 - satellite
	instrument8 - instrument
	satellite4 - satellite
	instrument9 - instrument
	satellite5 - satellite
	instrument10 - instrument
	instrument11 - instrument
	satellite6 - satellite
	instrument12 - instrument
	instrument13 - instrument
	instrument14 - instrument
	thermograph2 - mode
	spectrograph0 - mode
	image3 - mode
	thermograph4 - mode
	image1 - mode
	groundstation0 - direction
	groundstation3 - direction
	groundstation1 - direction
	groundstation4 - direction
	star5 - direction
	star2 - direction
	star6 - direction
	star7 - direction
	star8 - direction
	planet9 - direction
	star10 - direction
	star11 - direction
	star12 - direction
	star13 - direction
)
(:init
	(supports instrument0 image1)
	(supports instrument0 thermograph4)
	(supports instrument0 image3)
	(calibration_target instrument0 groundstation1)
	(supports instrument1 image1)
	(supports instrument1 thermograph2)
	(calibration_target instrument1 groundstation4)
	(calibration_target instrument1 star5)
	(supports instrument2 image3)
	(supports instrument2 thermograph2)
	(supports instrument2 thermograph4)
	(calibration_target instrument2 groundstation4)
	(calibration_target instrument2 groundstation3)
	(on_board instrument0 satellite0)
	(on_board instrument1 satellite0)
	(on_board instrument2 satellite0)
	(power_avail satellite0)
	(pointing satellite0 star5)
	(supports instrument3 image3)
	(calibration_target instrument3 star5)
	(calibration_target instrument3 groundstation0)
	(supports instrument4 thermograph2)
	(supports instrument4 thermograph4)
	(calibration_target instrument4 groundstation1)
	(supports instrument5 image1)
	(supports instrument5 spectrograph0)
	(calibration_target instrument5 groundstation1)
	(calibration_target instrument5 groundstation4)
	(on_board instrument3 satellite1)
	(on_board instrument4 satellite1)
	(on_board instrument5 satellite1)
	(power_avail satellite1)
	(pointing satellite1 star10)
	(supports instrument6 image3)
	(calibration_target instrument6 groundstation3)
	(calibration_target instrument6 groundstation1)
	(supports instrument7 image3)
	(supports instrument7 thermograph4)
	(supports instrument7 spectrograph0)
	(calibration_target instrument7 groundstation1)
	(calibration_target instrument7 groundstation3)
	(on_board instrument6 satellite2)
	(on_board instrument7 satellite2)
	(power_avail satellite2)
	(pointing satellite2 star6)
	(supports instrument8 spectrograph0)
	(supports instrument8 thermograph2)
	(supports instrument8 thermograph4)
	(calibration_target instrument8 groundstation1)
	(on_board instrument8 satellite3)
	(power_avail satellite3)
	(pointing satellite3 star2)
	(supports instrument9 image3)
	(calibration_target instrument9 star5)
	(on_board instrument9 satellite4)
	(power_avail satellite4)
	(pointing satellite4 star13)
	(supports instrument10 image1)
	(supports instrument10 thermograph2)
	(calibration_target instrument10 groundstation0)
	(calibration_target instrument10 star2)
	(supports instrument11 image3)
	(supports instrument11 spectrograph0)
	(supports instrument11 thermograph4)
	(calibration_target instrument11 groundstation3)
	(on_board instrument10 satellite5)
	(on_board instrument11 satellite5)
	(power_avail satellite5)
	(pointing satellite5 star7)
	(supports instrument12 thermograph2)
	(calibration_target instrument12 groundstation1)
	(calibration_target instrument12 groundstation3)
	(supports instrument13 image3)
	(calibration_target instrument13 groundstation4)
	(calibration_target instrument13 star5)
	(supports instrument14 image1)
	(calibration_target instrument14 star2)
	(calibration_target instrument14 star5)
	(on_board instrument12 satellite6)
	(on_board instrument13 satellite6)
	(on_board instrument14 satellite6)
	(power_avail satellite6)
	(pointing satellite6 star10)
)
(:goal (and
	(pointing satellite4 star7)
	(pointing satellite5 star10)
	(have_image star6 image1)
	(have_image star7 image1)
	(have_image star8 thermograph4)
	(have_image planet9 thermograph4)
	(have_image star10 thermograph4)
	(have_image star11 thermograph2)
	(have_image star12 thermograph4)
	(have_image star13 thermograph2)
))

)
