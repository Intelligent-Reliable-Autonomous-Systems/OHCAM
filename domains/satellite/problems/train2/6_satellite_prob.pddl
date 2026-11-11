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
	infrared0 - mode
	image1 - mode
	infrared3 - mode
	spectrograph2 - mode
	star4 - direction
	star3 - direction
	groundstation1 - direction
	groundstation0 - direction
	groundstation2 - direction
	planet5 - direction
	planet6 - direction
	star7 - direction
	planet8 - direction
	planet9 - direction
	phenomenon10 - direction
	star11 - direction
)
(:init
	(supports instrument0 spectrograph2)
	(supports instrument0 infrared3)
	(calibration_target instrument0 star3)
	(supports instrument1 infrared3)
	(supports instrument1 infrared0)
	(calibration_target instrument1 star3)
	(on_board instrument0 satellite0)
	(on_board instrument1 satellite0)
	(power_avail satellite0)
	(pointing satellite0 phenomenon10)
	(supports instrument2 image1)
	(supports instrument2 infrared3)
	(calibration_target instrument2 groundstation0)
	(on_board instrument2 satellite1)
	(power_avail satellite1)
	(pointing satellite1 phenomenon10)
	(supports instrument3 spectrograph2)
	(calibration_target instrument3 star3)
	(on_board instrument3 satellite2)
	(power_avail satellite2)
	(pointing satellite2 planet6)
	(supports instrument4 image1)
	(supports instrument4 infrared3)
	(supports instrument4 infrared0)
	(calibration_target instrument4 groundstation0)
	(supports instrument5 infrared3)
	(supports instrument5 infrared0)
	(calibration_target instrument5 groundstation1)
	(on_board instrument4 satellite3)
	(on_board instrument5 satellite3)
	(power_avail satellite3)
	(pointing satellite3 groundstation2)
	(supports instrument6 spectrograph2)
	(calibration_target instrument6 groundstation2)
	(supports instrument7 spectrograph2)
	(supports instrument7 infrared0)
	(supports instrument7 infrared3)
	(calibration_target instrument7 groundstation0)
	(on_board instrument6 satellite4)
	(on_board instrument7 satellite4)
	(power_avail satellite4)
	(pointing satellite4 planet5)
	(supports instrument8 infrared3)
	(supports instrument8 spectrograph2)
	(calibration_target instrument8 groundstation2)
	(on_board instrument8 satellite5)
	(power_avail satellite5)
	(pointing satellite5 star4)
)
(:goal (and
	(pointing satellite1 planet9)
	(pointing satellite3 planet5)
	(have_image planet5 infrared3)
	(have_image planet6 spectrograph2)
	(have_image star7 infrared3)
	(have_image planet8 spectrograph2)
	(have_image planet9 infrared3)
	(have_image phenomenon10 image1)
	(have_image star11 infrared0)
))

)
