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
	satellite5 - satellite
	instrument6 - instrument
	instrument7 - instrument
	infrared2 - mode
	spectrograph0 - mode
	spectrograph4 - mode
	infrared3 - mode
	spectrograph1 - mode
	groundstation2 - direction
	star4 - direction
	groundstation1 - direction
	star0 - direction
	groundstation3 - direction
	phenomenon5 - direction
	planet6 - direction
	star7 - direction
	planet8 - direction
	star9 - direction
	planet10 - direction
	planet11 - direction
)
(:init
	(supports instrument0 spectrograph4)
	(supports instrument0 spectrograph0)
	(supports instrument0 infrared3)
	(calibration_target instrument0 star0)
	(supports instrument1 spectrograph1)
	(supports instrument1 spectrograph4)
	(supports instrument1 infrared2)
	(calibration_target instrument1 groundstation1)
	(on_board instrument0 satellite0)
	(on_board instrument1 satellite0)
	(power_avail satellite0)
	(pointing satellite0 groundstation3)
	(supports instrument2 spectrograph4)
	(calibration_target instrument2 star4)
	(on_board instrument2 satellite1)
	(power_avail satellite1)
	(pointing satellite1 groundstation2)
	(supports instrument3 spectrograph4)
	(supports instrument3 spectrograph1)
	(supports instrument3 infrared3)
	(calibration_target instrument3 groundstation1)
	(on_board instrument3 satellite2)
	(power_avail satellite2)
	(pointing satellite2 star0)
	(supports instrument4 spectrograph0)
	(calibration_target instrument4 groundstation1)
	(on_board instrument4 satellite3)
	(power_avail satellite3)
	(pointing satellite3 groundstation1)
	(supports instrument5 spectrograph0)
	(supports instrument5 infrared3)
	(supports instrument5 spectrograph1)
	(calibration_target instrument5 star0)
	(on_board instrument5 satellite4)
	(power_avail satellite4)
	(pointing satellite4 star0)
	(supports instrument6 infrared2)
	(supports instrument6 spectrograph0)
	(supports instrument6 spectrograph1)
	(calibration_target instrument6 star0)
	(supports instrument7 spectrograph0)
	(supports instrument7 infrared2)
	(calibration_target instrument7 groundstation3)
	(on_board instrument6 satellite5)
	(on_board instrument7 satellite5)
	(power_avail satellite5)
	(pointing satellite5 star4)
)
(:goal (and
	(pointing satellite0 phenomenon5)
	(pointing satellite2 planet6)
	(pointing satellite3 groundstation3)
	(pointing satellite4 star9)
	(have_image phenomenon5 spectrograph1)
	(have_image planet6 spectrograph1)
	(have_image star7 infrared2)
	(have_image planet8 spectrograph1)
	(have_image star9 spectrograph0)
	(have_image planet10 infrared2)
	(have_image planet11 spectrograph4)
))

)
