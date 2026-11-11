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
	instrument5 - instrument
	satellite3 - satellite
	instrument6 - instrument
	instrument7 - instrument
	satellite4 - satellite
	instrument8 - instrument
	instrument9 - instrument
	instrument10 - instrument
	satellite5 - satellite
	instrument11 - instrument
	instrument12 - instrument
	satellite6 - satellite
	instrument13 - instrument
	infrared0 - mode
	spectrograph4 - mode
	thermograph1 - mode
	thermograph2 - mode
	infrared3 - mode
	groundstation1 - direction
	groundstation0 - direction
	groundstation2 - direction
	groundstation3 - direction
	star5 - direction
	groundstation4 - direction
	phenomenon6 - direction
	phenomenon7 - direction
	phenomenon8 - direction
	phenomenon9 - direction
	phenomenon10 - direction
	planet11 - direction
	planet12 - direction
	planet13 - direction
)
(:init
	(supports instrument0 thermograph2)
	(supports instrument0 infrared3)
	(calibration_target instrument0 groundstation0)
	(on_board instrument0 satellite0)
	(power_avail satellite0)
	(pointing satellite0 planet11)
	(supports instrument1 thermograph1)
	(supports instrument1 spectrograph4)
	(calibration_target instrument1 groundstation3)
	(supports instrument2 infrared0)
	(supports instrument2 spectrograph4)
	(supports instrument2 thermograph2)
	(calibration_target instrument2 groundstation1)
	(on_board instrument1 satellite1)
	(on_board instrument2 satellite1)
	(power_avail satellite1)
	(pointing satellite1 groundstation1)
	(supports instrument3 spectrograph4)
	(supports instrument3 infrared0)
	(supports instrument3 thermograph2)
	(calibration_target instrument3 groundstation1)
	(calibration_target instrument3 groundstation4)
	(supports instrument4 spectrograph4)
	(supports instrument4 thermograph2)
	(calibration_target instrument4 groundstation2)
	(calibration_target instrument4 groundstation1)
	(supports instrument5 infrared3)
	(supports instrument5 thermograph2)
	(calibration_target instrument5 groundstation3)
	(calibration_target instrument5 groundstation1)
	(on_board instrument3 satellite2)
	(on_board instrument4 satellite2)
	(on_board instrument5 satellite2)
	(power_avail satellite2)
	(pointing satellite2 planet12)
	(supports instrument6 thermograph2)
	(calibration_target instrument6 star5)
	(supports instrument7 infrared3)
	(supports instrument7 thermograph2)
	(calibration_target instrument7 groundstation3)
	(calibration_target instrument7 groundstation2)
	(on_board instrument6 satellite3)
	(on_board instrument7 satellite3)
	(power_avail satellite3)
	(pointing satellite3 planet13)
	(supports instrument8 thermograph1)
	(supports instrument8 thermograph2)
	(supports instrument8 infrared0)
	(calibration_target instrument8 star5)
	(calibration_target instrument8 groundstation0)
	(supports instrument9 infrared3)
	(supports instrument9 infrared0)
	(supports instrument9 thermograph2)
	(calibration_target instrument9 groundstation2)
	(calibration_target instrument9 groundstation1)
	(supports instrument10 spectrograph4)
	(calibration_target instrument10 star5)
	(calibration_target instrument10 groundstation0)
	(on_board instrument8 satellite4)
	(on_board instrument9 satellite4)
	(on_board instrument10 satellite4)
	(power_avail satellite4)
	(pointing satellite4 star5)
	(supports instrument11 thermograph1)
	(calibration_target instrument11 groundstation2)
	(calibration_target instrument11 groundstation0)
	(supports instrument12 thermograph2)
	(supports instrument12 thermograph1)
	(supports instrument12 spectrograph4)
	(calibration_target instrument12 star5)
	(calibration_target instrument12 groundstation3)
	(on_board instrument11 satellite5)
	(on_board instrument12 satellite5)
	(power_avail satellite5)
	(pointing satellite5 groundstation2)
	(supports instrument13 infrared3)
	(supports instrument13 thermograph1)
	(calibration_target instrument13 groundstation4)
	(on_board instrument13 satellite6)
	(power_avail satellite6)
	(pointing satellite6 planet13)
)
(:goal (and
	(pointing satellite0 groundstation4)
	(pointing satellite1 planet11)
	(have_image phenomenon6 thermograph2)
	(have_image phenomenon7 infrared0)
	(have_image phenomenon8 thermograph2)
	(have_image phenomenon9 infrared3)
	(have_image phenomenon10 thermograph1)
	(have_image planet11 spectrograph4)
	(have_image planet12 infrared0)
	(have_image planet13 infrared0)
))

)
