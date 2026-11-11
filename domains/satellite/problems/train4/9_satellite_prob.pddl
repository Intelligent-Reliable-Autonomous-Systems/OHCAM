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
	satellite3 - satellite
	instrument7 - instrument
	instrument8 - instrument
	satellite4 - satellite
	instrument9 - instrument
	instrument10 - instrument
	satellite5 - satellite
	instrument11 - instrument
	instrument12 - instrument
	instrument13 - instrument
	satellite6 - satellite
	instrument14 - instrument
	instrument15 - instrument
	instrument16 - instrument
	thermograph1 - mode
	image5 - mode
	spectrograph3 - mode
	infrared0 - mode
	infrared2 - mode
	thermograph4 - mode
	star2 - direction
	groundstation3 - direction
	groundstation4 - direction
	groundstation0 - direction
	groundstation1 - direction
	groundstation5 - direction
	star6 - direction
	planet7 - direction
	star8 - direction
	star9 - direction
	planet10 - direction
	star11 - direction
	phenomenon12 - direction
	phenomenon13 - direction
)
(:init
	(supports instrument0 image5)
	(supports instrument0 spectrograph3)
	(supports instrument0 infrared0)
	(calibration_target instrument0 groundstation1)
	(supports instrument1 spectrograph3)
	(calibration_target instrument1 groundstation4)
	(supports instrument2 image5)
	(calibration_target instrument2 groundstation4)
	(calibration_target instrument2 groundstation1)
	(on_board instrument0 satellite0)
	(on_board instrument1 satellite0)
	(on_board instrument2 satellite0)
	(power_avail satellite0)
	(pointing satellite0 star6)
	(supports instrument3 thermograph4)
	(calibration_target instrument3 groundstation3)
	(calibration_target instrument3 star2)
	(supports instrument4 thermograph1)
	(supports instrument4 infrared2)
	(calibration_target instrument4 groundstation1)
	(calibration_target instrument4 groundstation0)
	(supports instrument5 image5)
	(supports instrument5 infrared2)
	(supports instrument5 spectrograph3)
	(calibration_target instrument5 groundstation0)
	(calibration_target instrument5 groundstation4)
	(on_board instrument3 satellite1)
	(on_board instrument4 satellite1)
	(on_board instrument5 satellite1)
	(power_avail satellite1)
	(pointing satellite1 star2)
	(supports instrument6 thermograph4)
	(calibration_target instrument6 groundstation3)
	(on_board instrument6 satellite2)
	(power_avail satellite2)
	(pointing satellite2 star8)
	(supports instrument7 thermograph1)
	(supports instrument7 thermograph4)
	(calibration_target instrument7 groundstation0)
	(supports instrument8 thermograph4)
	(supports instrument8 infrared2)
	(calibration_target instrument8 groundstation0)
	(calibration_target instrument8 groundstation3)
	(on_board instrument7 satellite3)
	(on_board instrument8 satellite3)
	(power_avail satellite3)
	(pointing satellite3 planet7)
	(supports instrument9 thermograph1)
	(supports instrument9 thermograph4)
	(supports instrument9 image5)
	(calibration_target instrument9 groundstation0)
	(calibration_target instrument9 groundstation4)
	(supports instrument10 infrared2)
	(calibration_target instrument10 star2)
	(calibration_target instrument10 groundstation4)
	(on_board instrument9 satellite4)
	(on_board instrument10 satellite4)
	(power_avail satellite4)
	(pointing satellite4 groundstation3)
	(supports instrument11 thermograph4)
	(supports instrument11 image5)
	(calibration_target instrument11 groundstation4)
	(calibration_target instrument11 groundstation3)
	(supports instrument12 thermograph1)
	(supports instrument12 thermograph4)
	(calibration_target instrument12 groundstation5)
	(supports instrument13 spectrograph3)
	(supports instrument13 infrared2)
	(supports instrument13 thermograph1)
	(calibration_target instrument13 groundstation0)
	(calibration_target instrument13 groundstation1)
	(on_board instrument11 satellite5)
	(on_board instrument12 satellite5)
	(on_board instrument13 satellite5)
	(power_avail satellite5)
	(pointing satellite5 groundstation3)
	(supports instrument14 infrared0)
	(supports instrument14 thermograph4)
	(calibration_target instrument14 groundstation1)
	(supports instrument15 spectrograph3)
	(supports instrument15 image5)
	(calibration_target instrument15 groundstation1)
	(calibration_target instrument15 groundstation0)
	(supports instrument16 image5)
	(supports instrument16 infrared2)
	(calibration_target instrument16 groundstation5)
	(on_board instrument14 satellite6)
	(on_board instrument15 satellite6)
	(on_board instrument16 satellite6)
	(power_avail satellite6)
	(pointing satellite6 groundstation5)
)
(:goal (and
	(pointing satellite0 groundstation4)
	(pointing satellite3 groundstation5)
	(pointing satellite5 groundstation1)
	(have_image star6 spectrograph3)
	(have_image planet7 infrared0)
	(have_image star8 thermograph4)
	(have_image star9 infrared0)
	(have_image star9 thermograph1)
	(have_image planet10 thermograph4)
	(have_image planet10 thermograph1)
	(have_image star11 image5)
	(have_image phenomenon12 thermograph4)
	(have_image phenomenon13 thermograph1)
))

)
