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
	satellite6 - satellite
	instrument12 - instrument
	instrument13 - instrument
	spectrograph5 - mode
	image1 - mode
	image0 - mode
	thermograph4 - mode
	spectrograph3 - mode
	thermograph2 - mode
	star5 - direction
	groundstation0 - direction
	groundstation2 - direction
	groundstation4 - direction
	groundstation1 - direction
	groundstation3 - direction
	planet6 - direction
	star7 - direction
	star8 - direction
	phenomenon9 - direction
	planet10 - direction
	phenomenon11 - direction
	phenomenon12 - direction
	star13 - direction
)
(:init
	(supports instrument0 thermograph2)
	(supports instrument0 spectrograph5)
	(calibration_target instrument0 star5)
	(calibration_target instrument0 groundstation1)
	(supports instrument1 thermograph4)
	(supports instrument1 image0)
	(supports instrument1 thermograph2)
	(calibration_target instrument1 groundstation2)
	(calibration_target instrument1 groundstation1)
	(on_board instrument0 satellite0)
	(on_board instrument1 satellite0)
	(power_avail satellite0)
	(pointing satellite0 phenomenon12)
	(supports instrument2 spectrograph3)
	(supports instrument2 thermograph4)
	(supports instrument2 image0)
	(calibration_target instrument2 groundstation4)
	(calibration_target instrument2 star5)
	(on_board instrument2 satellite1)
	(power_avail satellite1)
	(pointing satellite1 phenomenon12)
	(supports instrument3 spectrograph5)
	(supports instrument3 image0)
	(supports instrument3 thermograph4)
	(calibration_target instrument3 groundstation0)
	(supports instrument4 spectrograph5)
	(supports instrument4 thermograph2)
	(supports instrument4 spectrograph3)
	(calibration_target instrument4 groundstation2)
	(calibration_target instrument4 groundstation0)
	(supports instrument5 spectrograph5)
	(calibration_target instrument5 groundstation2)
	(on_board instrument3 satellite2)
	(on_board instrument4 satellite2)
	(on_board instrument5 satellite2)
	(power_avail satellite2)
	(pointing satellite2 planet6)
	(supports instrument6 image1)
	(supports instrument6 image0)
	(supports instrument6 spectrograph5)
	(calibration_target instrument6 groundstation2)
	(supports instrument7 image1)
	(supports instrument7 thermograph4)
	(supports instrument7 spectrograph5)
	(calibration_target instrument7 star5)
	(calibration_target instrument7 groundstation3)
	(on_board instrument6 satellite3)
	(on_board instrument7 satellite3)
	(power_avail satellite3)
	(pointing satellite3 star8)
	(supports instrument8 thermograph2)
	(calibration_target instrument8 groundstation4)
	(supports instrument9 spectrograph3)
	(supports instrument9 spectrograph5)
	(calibration_target instrument9 groundstation0)
	(supports instrument10 thermograph2)
	(calibration_target instrument10 groundstation3)
	(calibration_target instrument10 groundstation2)
	(on_board instrument8 satellite4)
	(on_board instrument9 satellite4)
	(on_board instrument10 satellite4)
	(power_avail satellite4)
	(pointing satellite4 star13)
	(supports instrument11 spectrograph3)
	(calibration_target instrument11 groundstation1)
	(on_board instrument11 satellite5)
	(power_avail satellite5)
	(pointing satellite5 groundstation4)
	(supports instrument12 spectrograph5)
	(supports instrument12 spectrograph3)
	(calibration_target instrument12 groundstation4)
	(calibration_target instrument12 groundstation1)
	(supports instrument13 thermograph2)
	(supports instrument13 thermograph4)
	(calibration_target instrument13 groundstation3)
	(calibration_target instrument13 groundstation1)
	(on_board instrument12 satellite6)
	(on_board instrument13 satellite6)
	(power_avail satellite6)
	(pointing satellite6 planet6)
)
(:goal (and
	(pointing satellite1 planet6)
	(pointing satellite3 groundstation4)
	(pointing satellite5 star7)
	(pointing satellite6 star5)
	(have_image planet6 spectrograph3)
	(have_image planet6 thermograph2)
	(have_image star7 image0)
	(have_image star8 spectrograph3)
	(have_image star8 spectrograph5)
	(have_image phenomenon9 spectrograph5)
	(have_image planet10 image1)
	(have_image planet10 thermograph2)
	(have_image phenomenon11 image1)
	(have_image phenomenon12 spectrograph3)
	(have_image star13 thermograph4)
))

)
