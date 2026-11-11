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
	instrument4 - instrument
	satellite3 - satellite
	instrument5 - instrument
	satellite4 - satellite
	instrument6 - instrument
	image1 - mode
	infrared3 - mode
	spectrograph0 - mode
	infrared2 - mode
	groundstation1 - direction
	star0 - direction
	groundstation3 - direction
	star2 - direction
	phenomenon4 - direction
	planet5 - direction
	phenomenon6 - direction
	star7 - direction
	star8 - direction
	phenomenon9 - direction
)
(:init
	(supports instrument0 infrared2)
	(calibration_target instrument0 groundstation3)
	(supports instrument1 infrared3)
	(supports instrument1 infrared2)
	(calibration_target instrument1 groundstation1)
	(on_board instrument0 satellite0)
	(on_board instrument1 satellite0)
	(power_avail satellite0)
	(pointing satellite0 groundstation1)
	(supports instrument2 infrared3)
	(supports instrument2 spectrograph0)
	(supports instrument2 image1)
	(calibration_target instrument2 groundstation3)
	(on_board instrument2 satellite1)
	(power_avail satellite1)
	(pointing satellite1 star7)
	(supports instrument3 image1)
	(supports instrument3 spectrograph0)
	(calibration_target instrument3 groundstation3)
	(supports instrument4 image1)
	(calibration_target instrument4 star0)
	(on_board instrument3 satellite2)
	(on_board instrument4 satellite2)
	(power_avail satellite2)
	(pointing satellite2 groundstation3)
	(supports instrument5 image1)
	(supports instrument5 infrared3)
	(calibration_target instrument5 groundstation3)
	(on_board instrument5 satellite3)
	(power_avail satellite3)
	(pointing satellite3 star8)
	(supports instrument6 infrared2)
	(supports instrument6 image1)
	(calibration_target instrument6 star2)
	(on_board instrument6 satellite4)
	(power_avail satellite4)
	(pointing satellite4 groundstation1)
)
(:goal (and
	(pointing satellite4 phenomenon9)
	(have_image phenomenon4 infrared3)
	(have_image planet5 spectrograph0)
	(have_image phenomenon6 image1)
	(have_image star7 infrared2)
	(have_image star8 spectrograph0)
	(have_image phenomenon9 infrared2)
))

)
