(define (problem strips-sat-x-1)
(:domain satellite)
(:objects
	satellite0 - satellite
	instrument0 - instrument
	instrument1 - instrument
	satellite1 - satellite
	instrument2 - instrument
	instrument3 - instrument
	instrument4 - instrument
	satellite2 - satellite
	instrument5 - instrument
	instrument6 - instrument
	instrument7 - instrument
	satellite3 - satellite
	instrument8 - instrument
	instrument9 - instrument
	instrument10 - instrument
	satellite4 - satellite
	instrument11 - instrument
	satellite5 - satellite
	instrument12 - instrument
	satellite6 - satellite
	instrument13 - instrument
	instrument14 - instrument
	instrument15 - instrument
	spectrograph3 - mode
	infrared2 - mode
	thermograph0 - mode
	spectrograph4 - mode
	infrared5 - mode
	thermograph1 - mode
	star5 - direction
	star4 - direction
	star2 - direction
	star1 - direction
	groundstation0 - direction
	star3 - direction
	planet6 - direction
	phenomenon7 - direction
	star8 - direction
	star9 - direction
	phenomenon10 - direction
	phenomenon11 - direction
	phenomenon12 - direction
	phenomenon13 - direction
)
(:init
	(supports instrument0 infrared5)
	(supports instrument0 thermograph0)
	(calibration_target instrument0 star1)
	(calibration_target instrument0 star2)
	(supports instrument1 spectrograph3)
	(supports instrument1 thermograph0)
	(calibration_target instrument1 star1)
	(on_board instrument0 satellite0)
	(on_board instrument1 satellite0)
	(power_avail satellite0)
	(pointing satellite0 star2)
	(supports instrument2 spectrograph3)
	(supports instrument2 spectrograph4)
	(supports instrument2 thermograph0)
	(calibration_target instrument2 star1)
	(supports instrument3 infrared2)
	(supports instrument3 spectrograph3)
	(calibration_target instrument3 star5)
	(calibration_target instrument3 star2)
	(supports instrument4 spectrograph4)
	(supports instrument4 infrared5)
	(supports instrument4 thermograph0)
	(calibration_target instrument4 star5)
	(calibration_target instrument4 star1)
	(on_board instrument2 satellite1)
	(on_board instrument3 satellite1)
	(on_board instrument4 satellite1)
	(power_avail satellite1)
	(pointing satellite1 phenomenon10)
	(supports instrument5 spectrograph4)
	(supports instrument5 spectrograph3)
	(supports instrument5 infrared5)
	(calibration_target instrument5 star3)
	(supports instrument6 infrared5)
	(supports instrument6 thermograph1)
	(calibration_target instrument6 star4)
	(supports instrument7 infrared2)
	(supports instrument7 spectrograph4)
	(calibration_target instrument7 star2)
	(on_board instrument5 satellite2)
	(on_board instrument6 satellite2)
	(on_board instrument7 satellite2)
	(power_avail satellite2)
	(pointing satellite2 star3)
	(supports instrument8 thermograph0)
	(supports instrument8 spectrograph3)
	(calibration_target instrument8 star2)
	(supports instrument9 spectrograph4)
	(calibration_target instrument9 star5)
	(calibration_target instrument9 star3)
	(supports instrument10 thermograph1)
	(calibration_target instrument10 star4)
	(on_board instrument8 satellite3)
	(on_board instrument9 satellite3)
	(on_board instrument10 satellite3)
	(power_avail satellite3)
	(pointing satellite3 phenomenon7)
	(supports instrument11 thermograph1)
	(calibration_target instrument11 star3)
	(calibration_target instrument11 star4)
	(on_board instrument11 satellite4)
	(power_avail satellite4)
	(pointing satellite4 star9)
	(supports instrument12 infrared5)
	(calibration_target instrument12 groundstation0)
	(calibration_target instrument12 star1)
	(on_board instrument12 satellite5)
	(power_avail satellite5)
	(pointing satellite5 phenomenon10)
	(supports instrument13 spectrograph3)
	(supports instrument13 infrared5)
	(calibration_target instrument13 star2)
	(calibration_target instrument13 star3)
	(supports instrument14 thermograph0)
	(calibration_target instrument14 groundstation0)
	(calibration_target instrument14 star1)
	(supports instrument15 spectrograph3)
	(calibration_target instrument15 star3)
	(on_board instrument13 satellite6)
	(on_board instrument14 satellite6)
	(on_board instrument15 satellite6)
	(power_avail satellite6)
	(pointing satellite6 phenomenon7)
)
(:goal (and
	(pointing satellite0 phenomenon10)
	(pointing satellite1 star2)
	(pointing satellite2 planet6)
	(have_image planet6 thermograph1)
	(have_image planet6 thermograph0)
	(have_image phenomenon7 infrared2)
	(have_image star8 thermograph0)
	(have_image star9 spectrograph4)
	(have_image phenomenon10 thermograph0)
	(have_image phenomenon10 infrared2)
	(have_image phenomenon11 spectrograph4)
	(have_image phenomenon12 spectrograph4)
	(have_image phenomenon13 spectrograph4)
	(have_image phenomenon13 thermograph0)
))

)
