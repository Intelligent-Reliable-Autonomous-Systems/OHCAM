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
	satellite4 - satellite
	instrument5 - instrument
	instrument6 - instrument
	satellite5 - satellite
	instrument7 - instrument
	image3 - mode
	spectrograph1 - mode
	infrared2 - mode
	thermograph0 - mode
	star3 - direction
	star4 - direction
	groundstation0 - direction
	star2 - direction
	star1 - direction
	phenomenon5 - direction
	planet6 - direction
	star7 - direction
	planet8 - direction
	phenomenon9 - direction
	planet10 - direction
	phenomenon11 - direction
)
(:init
	(supports instrument0 infrared2)
	(calibration_target instrument0 groundstation0)
	(supports instrument1 thermograph0)
	(calibration_target instrument1 star2)
	(on_board instrument0 satellite0)
	(on_board instrument1 satellite0)
	(power_avail satellite0)
	(pointing satellite0 phenomenon11)
	(supports instrument2 thermograph0)
	(supports instrument2 infrared2)
	(supports instrument2 spectrograph1)
	(calibration_target instrument2 star4)
	(on_board instrument2 satellite1)
	(power_avail satellite1)
	(pointing satellite1 phenomenon11)
	(supports instrument3 spectrograph1)
	(supports instrument3 infrared2)
	(calibration_target instrument3 star1)
	(on_board instrument3 satellite2)
	(power_avail satellite2)
	(pointing satellite2 star3)
	(supports instrument4 image3)
	(supports instrument4 spectrograph1)
	(supports instrument4 thermograph0)
	(calibration_target instrument4 star4)
	(on_board instrument4 satellite3)
	(power_avail satellite3)
	(pointing satellite3 star3)
	(supports instrument5 thermograph0)
	(calibration_target instrument5 groundstation0)
	(supports instrument6 image3)
	(calibration_target instrument6 star2)
	(on_board instrument5 satellite4)
	(on_board instrument6 satellite4)
	(power_avail satellite4)
	(pointing satellite4 groundstation0)
	(supports instrument7 image3)
	(calibration_target instrument7 star1)
	(on_board instrument7 satellite5)
	(power_avail satellite5)
	(pointing satellite5 planet6)
)
(:goal (and
	(pointing satellite0 star7)
	(pointing satellite1 planet10)
	(pointing satellite5 phenomenon11)
	(have_image phenomenon5 spectrograph1)
	(have_image planet6 image3)
	(have_image star7 spectrograph1)
	(have_image planet8 image3)
	(have_image phenomenon9 spectrograph1)
	(have_image planet10 thermograph0)
	(have_image phenomenon11 image3)
))

)
