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
	satellite3 - satellite
	instrument4 - instrument
	instrument5 - instrument
	satellite4 - satellite
	instrument6 - instrument
	instrument7 - instrument
	satellite5 - satellite
	instrument8 - instrument
	instrument9 - instrument
	instrument10 - instrument
	satellite6 - satellite
	instrument11 - instrument
	instrument12 - instrument
	instrument13 - instrument
	thermograph1 - mode
	spectrograph3 - mode
	thermograph4 - mode
	image0 - mode
	infrared2 - mode
	groundstation4 - direction
	star3 - direction
	star5 - direction
	star0 - direction
	groundstation1 - direction
	star2 - direction
	phenomenon6 - direction
	star7 - direction
	star8 - direction
	phenomenon9 - direction
	planet10 - direction
	planet11 - direction
	phenomenon12 - direction
	star13 - direction
)
(:init
	(supports instrument0 image0)
	(calibration_target instrument0 star0)
	(supports instrument1 thermograph4)
	(calibration_target instrument1 star5)
	(on_board instrument0 satellite0)
	(on_board instrument1 satellite0)
	(power_avail satellite0)
	(pointing satellite0 groundstation4)
	(supports instrument2 spectrograph3)
	(calibration_target instrument2 star5)
	(calibration_target instrument2 star3)
	(on_board instrument2 satellite1)
	(power_avail satellite1)
	(pointing satellite1 groundstation1)
	(supports instrument3 spectrograph3)
	(calibration_target instrument3 star2)
	(on_board instrument3 satellite2)
	(power_avail satellite2)
	(pointing satellite2 planet10)
	(supports instrument4 thermograph1)
	(supports instrument4 infrared2)
	(supports instrument4 spectrograph3)
	(calibration_target instrument4 groundstation4)
	(calibration_target instrument4 star2)
	(supports instrument5 thermograph4)
	(calibration_target instrument5 star2)
	(on_board instrument4 satellite3)
	(on_board instrument5 satellite3)
	(power_avail satellite3)
	(pointing satellite3 planet10)
	(supports instrument6 image0)
	(calibration_target instrument6 groundstation4)
	(supports instrument7 spectrograph3)
	(supports instrument7 thermograph4)
	(supports instrument7 infrared2)
	(calibration_target instrument7 star3)
	(calibration_target instrument7 star5)
	(on_board instrument6 satellite4)
	(on_board instrument7 satellite4)
	(power_avail satellite4)
	(pointing satellite4 phenomenon9)
	(supports instrument8 thermograph1)
	(supports instrument8 thermograph4)
	(calibration_target instrument8 star5)
	(supports instrument9 infrared2)
	(supports instrument9 image0)
	(supports instrument9 thermograph4)
	(calibration_target instrument9 star0)
	(supports instrument10 spectrograph3)
	(calibration_target instrument10 star2)
	(on_board instrument8 satellite5)
	(on_board instrument9 satellite5)
	(on_board instrument10 satellite5)
	(power_avail satellite5)
	(pointing satellite5 phenomenon6)
	(supports instrument11 thermograph4)
	(supports instrument11 image0)
	(supports instrument11 spectrograph3)
	(calibration_target instrument11 groundstation1)
	(calibration_target instrument11 star0)
	(supports instrument12 spectrograph3)
	(supports instrument12 thermograph4)
	(supports instrument12 infrared2)
	(calibration_target instrument12 groundstation1)
	(calibration_target instrument12 star0)
	(supports instrument13 infrared2)
	(supports instrument13 thermograph1)
	(calibration_target instrument13 star2)
	(calibration_target instrument13 groundstation1)
	(on_board instrument11 satellite6)
	(on_board instrument12 satellite6)
	(on_board instrument13 satellite6)
	(power_avail satellite6)
	(pointing satellite6 phenomenon12)
)
(:goal (and
	(pointing satellite0 star7)
	(pointing satellite5 star2)
	(have_image phenomenon6 thermograph1)
	(have_image star7 thermograph4)
	(have_image star8 thermograph1)
	(have_image phenomenon9 infrared2)
	(have_image planet10 thermograph1)
	(have_image planet11 image0)
	(have_image phenomenon12 image0)
	(have_image star13 image0)
))

)
