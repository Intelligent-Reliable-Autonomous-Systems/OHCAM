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
	satellite3 - satellite
	instrument4 - instrument
	image1 - mode
	image0 - mode
	image2 - mode
	groundstation1 - direction
	star2 - direction
	groundstation0 - direction
	phenomenon3 - direction
	phenomenon4 - direction
	phenomenon5 - direction
	phenomenon6 - direction
	phenomenon7 - direction
)
(:init
	(supports instrument0 image2)
	(supports instrument0 image0)
	(supports instrument0 image1)
	(calibration_target instrument0 groundstation0)
	(on_board instrument0 satellite0)
	(power_avail satellite0)
	(pointing satellite0 groundstation0)
	(supports instrument1 image1)
	(supports instrument1 image2)
	(supports instrument1 image0)
	(calibration_target instrument1 groundstation0)
	(supports instrument2 image2)
	(supports instrument2 image1)
	(calibration_target instrument2 star2)
	(on_board instrument1 satellite1)
	(on_board instrument2 satellite1)
	(power_avail satellite1)
	(pointing satellite1 phenomenon6)
	(supports instrument3 image0)
	(supports instrument3 image2)
	(supports instrument3 image1)
	(calibration_target instrument3 groundstation0)
	(on_board instrument3 satellite2)
	(power_avail satellite2)
	(pointing satellite2 phenomenon4)
	(supports instrument4 image2)
	(supports instrument4 image1)
	(calibration_target instrument4 groundstation0)
	(on_board instrument4 satellite3)
	(power_avail satellite3)
	(pointing satellite3 phenomenon6)
)
(:goal (and
	(pointing satellite2 phenomenon3)
	(have_image phenomenon3 image0)
	(have_image phenomenon4 image0)
	(have_image phenomenon5 image1)
	(have_image phenomenon6 image2)
	(have_image phenomenon7 image2)
))

)
