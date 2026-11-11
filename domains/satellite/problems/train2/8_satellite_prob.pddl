(define (problem strips-sat-x-1)
(:domain satellite)
(:objects
	satellite0 - satellite
	instrument0 - instrument
	satellite1 - satellite
	instrument1 - instrument
	instrument2 - instrument
	satellite2 - satellite
	instrument3 - instrument
	instrument4 - instrument
	satellite3 - satellite
	instrument5 - instrument
	instrument6 - instrument
	instrument7 - instrument
	satellite4 - satellite
	instrument8 - instrument
	satellite5 - satellite
	instrument9 - instrument
	instrument10 - instrument
	satellite6 - satellite
	instrument11 - instrument
	instrument12 - instrument
	image3 - mode
	spectrograph4 - mode
	infrared2 - mode
	image0 - mode
	thermograph1 - mode
	star4 - direction
	star0 - direction
	groundstation2 - direction
	star3 - direction
	star1 - direction
	groundstation5 - direction
	star6 - direction
	phenomenon7 - direction
	phenomenon8 - direction
	phenomenon9 - direction
	phenomenon10 - direction
	planet11 - direction
	planet12 - direction
	star13 - direction
)
(:init
	(supports instrument0 infrared2)
	(supports instrument0 spectrograph4)
	(calibration_target instrument0 star1)
	(on_board instrument0 satellite0)
	(power_avail satellite0)
	(pointing satellite0 phenomenon10)
	(supports instrument1 infrared2)
	(supports instrument1 image3)
	(calibration_target instrument1 groundstation5)
	(calibration_target instrument1 star4)
	(supports instrument2 infrared2)
	(calibration_target instrument2 groundstation5)
	(on_board instrument1 satellite1)
	(on_board instrument2 satellite1)
	(power_avail satellite1)
	(pointing satellite1 planet12)
	(supports instrument3 infrared2)
	(calibration_target instrument3 star0)
	(calibration_target instrument3 star1)
	(supports instrument4 spectrograph4)
	(supports instrument4 infrared2)
	(calibration_target instrument4 groundstation2)
	(calibration_target instrument4 star0)
	(on_board instrument3 satellite2)
	(on_board instrument4 satellite2)
	(power_avail satellite2)
	(pointing satellite2 phenomenon10)
	(supports instrument5 thermograph1)
	(calibration_target instrument5 groundstation2)
	(calibration_target instrument5 star4)
	(supports instrument6 image3)
	(supports instrument6 spectrograph4)
	(supports instrument6 thermograph1)
	(calibration_target instrument6 star4)
	(supports instrument7 infrared2)
	(supports instrument7 spectrograph4)
	(supports instrument7 image0)
	(calibration_target instrument7 star0)
	(on_board instrument5 satellite3)
	(on_board instrument6 satellite3)
	(on_board instrument7 satellite3)
	(power_avail satellite3)
	(pointing satellite3 phenomenon8)
	(supports instrument8 spectrograph4)
	(calibration_target instrument8 star1)
	(on_board instrument8 satellite4)
	(power_avail satellite4)
	(pointing satellite4 phenomenon8)
	(supports instrument9 thermograph1)
	(supports instrument9 infrared2)
	(calibration_target instrument9 groundstation2)
	(supports instrument10 image3)
	(supports instrument10 infrared2)
	(supports instrument10 thermograph1)
	(calibration_target instrument10 star3)
	(calibration_target instrument10 groundstation2)
	(on_board instrument9 satellite5)
	(on_board instrument10 satellite5)
	(power_avail satellite5)
	(pointing satellite5 phenomenon8)
	(supports instrument11 image0)
	(calibration_target instrument11 star1)
	(supports instrument12 infrared2)
	(supports instrument12 thermograph1)
	(calibration_target instrument12 groundstation5)
	(on_board instrument11 satellite6)
	(on_board instrument12 satellite6)
	(power_avail satellite6)
	(pointing satellite6 planet11)
)
(:goal (and
	(have_image star6 spectrograph4)
	(have_image phenomenon7 spectrograph4)
	(have_image phenomenon8 spectrograph4)
	(have_image phenomenon9 image0)
	(have_image phenomenon10 infrared2)
	(have_image planet11 infrared2)
	(have_image planet12 image3)
	(have_image star13 image3)
))

)
