(define (problem strips-sat-x-1)
(:domain satellite)
(:objects
	satellite0 - satellite
	instrument0 - instrument
	satellite1 - satellite
	instrument1 - instrument
	instrument2 - instrument
	instrument3 - instrument
	satellite2 - satellite
	instrument4 - instrument
	satellite3 - satellite
	instrument5 - instrument
	satellite4 - satellite
	instrument6 - instrument
	instrument7 - instrument
	satellite5 - satellite
	instrument8 - instrument
	satellite6 - satellite
	instrument9 - instrument
	instrument10 - instrument
	infrared5 - mode
	spectrograph2 - mode
	thermograph4 - mode
	infrared3 - mode
	thermograph0 - mode
	spectrograph1 - mode
	groundstation2 - direction
	groundstation3 - direction
	star5 - direction
	groundstation0 - direction
	groundstation4 - direction
	groundstation1 - direction
	planet6 - direction
	planet7 - direction
	phenomenon8 - direction
	phenomenon9 - direction
	star10 - direction
	phenomenon11 - direction
	phenomenon12 - direction
	phenomenon13 - direction
)
(:init
	(supports instrument0 thermograph0)
	(supports instrument0 thermograph4)
	(calibration_target instrument0 groundstation3)
	(on_board instrument0 satellite0)
	(power_avail satellite0)
	(pointing satellite0 groundstation3)
	(supports instrument1 thermograph0)
	(calibration_target instrument1 star5)
	(supports instrument2 thermograph4)
	(calibration_target instrument2 groundstation4)
	(calibration_target instrument2 star5)
	(supports instrument3 spectrograph1)
	(supports instrument3 infrared3)
	(calibration_target instrument3 star5)
	(calibration_target instrument3 groundstation1)
	(on_board instrument1 satellite1)
	(on_board instrument2 satellite1)
	(on_board instrument3 satellite1)
	(power_avail satellite1)
	(pointing satellite1 phenomenon8)
	(supports instrument4 thermograph4)
	(calibration_target instrument4 groundstation1)
	(calibration_target instrument4 groundstation4)
	(on_board instrument4 satellite2)
	(power_avail satellite2)
	(pointing satellite2 groundstation3)
	(supports instrument5 thermograph4)
	(calibration_target instrument5 groundstation4)
	(calibration_target instrument5 groundstation0)
	(on_board instrument5 satellite3)
	(power_avail satellite3)
	(pointing satellite3 phenomenon13)
	(supports instrument6 spectrograph2)
	(supports instrument6 thermograph4)
	(calibration_target instrument6 groundstation4)
	(calibration_target instrument6 star5)
	(supports instrument7 spectrograph1)
	(supports instrument7 thermograph0)
	(supports instrument7 spectrograph2)
	(calibration_target instrument7 groundstation0)
	(calibration_target instrument7 groundstation1)
	(on_board instrument6 satellite4)
	(on_board instrument7 satellite4)
	(power_avail satellite4)
	(pointing satellite4 groundstation2)
	(supports instrument8 thermograph4)
	(calibration_target instrument8 groundstation1)
	(on_board instrument8 satellite5)
	(power_avail satellite5)
	(pointing satellite5 phenomenon11)
	(supports instrument9 spectrograph2)
	(supports instrument9 infrared5)
	(calibration_target instrument9 groundstation1)
	(supports instrument10 spectrograph2)
	(calibration_target instrument10 groundstation1)
	(calibration_target instrument10 groundstation4)
	(on_board instrument9 satellite6)
	(on_board instrument10 satellite6)
	(power_avail satellite6)
	(pointing satellite6 groundstation3)
)
(:goal (and
	(pointing satellite0 groundstation0)
	(pointing satellite2 groundstation0)
	(pointing satellite6 star5)
	(have_image planet6 spectrograph1)
	(have_image planet6 spectrograph2)
	(have_image planet7 spectrograph1)
	(have_image planet7 thermograph4)
	(have_image phenomenon8 spectrograph2)
	(have_image phenomenon9 spectrograph2)
	(have_image star10 spectrograph1)
	(have_image phenomenon11 thermograph0)
	(have_image phenomenon12 spectrograph1)
	(have_image phenomenon12 spectrograph2)
	(have_image phenomenon13 thermograph0)
	(have_image phenomenon13 thermograph4)
))

)
