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
	spectrograph0 - mode
	thermograph3 - mode
	thermograph2 - mode
	thermograph1 - mode
	groundstation4 - direction
	groundstation1 - direction
	star2 - direction
	groundstation0 - direction
	groundstation3 - direction
	planet5 - direction
	planet6 - direction
	phenomenon7 - direction
	planet8 - direction
	star9 - direction
	star10 - direction
	planet11 - direction
)
(:init
	(supports instrument0 thermograph2)
	(supports instrument0 thermograph1)
	(supports instrument0 spectrograph0)
	(calibration_target instrument0 groundstation1)
	(supports instrument1 thermograph1)
	(calibration_target instrument1 groundstation1)
	(on_board instrument0 satellite0)
	(on_board instrument1 satellite0)
	(power_avail satellite0)
	(pointing satellite0 groundstation0)
	(supports instrument2 thermograph2)
	(supports instrument2 thermograph1)
	(calibration_target instrument2 groundstation0)
	(supports instrument3 thermograph2)
	(supports instrument3 thermograph3)
	(calibration_target instrument3 star2)
	(on_board instrument2 satellite1)
	(on_board instrument3 satellite1)
	(power_avail satellite1)
	(pointing satellite1 groundstation4)
	(supports instrument4 thermograph2)
	(supports instrument4 thermograph3)
	(calibration_target instrument4 groundstation3)
	(on_board instrument4 satellite2)
	(power_avail satellite2)
	(pointing satellite2 planet5)
	(supports instrument5 spectrograph0)
	(supports instrument5 thermograph1)
	(supports instrument5 thermograph2)
	(calibration_target instrument5 groundstation0)
	(supports instrument6 thermograph2)
	(supports instrument6 spectrograph0)
	(calibration_target instrument6 groundstation0)
	(on_board instrument5 satellite3)
	(on_board instrument6 satellite3)
	(power_avail satellite3)
	(pointing satellite3 star2)
	(supports instrument7 thermograph2)
	(supports instrument7 thermograph3)
	(supports instrument7 spectrograph0)
	(calibration_target instrument7 groundstation3)
	(on_board instrument7 satellite4)
	(power_avail satellite4)
	(pointing satellite4 groundstation3)
	(supports instrument8 thermograph1)
	(calibration_target instrument8 groundstation3)
	(on_board instrument8 satellite5)
	(power_avail satellite5)
	(pointing satellite5 groundstation0)
)
(:goal (and
	(pointing satellite1 star10)
	(pointing satellite2 planet11)
	(pointing satellite3 phenomenon7)
	(pointing satellite4 groundstation1)
	(have_image planet5 spectrograph0)
	(have_image planet6 thermograph3)
	(have_image phenomenon7 thermograph1)
	(have_image planet8 thermograph1)
	(have_image star9 spectrograph0)
	(have_image star10 thermograph3)
	(have_image planet11 thermograph2)
))

)
