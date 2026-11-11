(define (problem spongeworld-task4)
(:domain spongeworld)
(:objects
    blue_circle purple_circle red_circle green_circle - target
    table_0 - table
    large_white_circle - plate
    blue_water_spill marker_scribble - spill
    blue_sponge yellow_sponge - sponge
    red_can blue_can - can)
(:init
    (on blue_sponge blue_circle)
    (on blue_circle table_0)
    (obstructed blue_circle)

    (on green_circle table_0)

    (on purple_circle table_0)

    (on red_circle table_0)
    (on yellow_sponge red_circle)
    (obstructed red_circle)

    ; plate
    (on large_white_circle table_0)
    (on marker_scribble large_white_circle)
    (on blue_can large_white_circle)
    (on red_can large_white_circle)
    (obstructed large_white_circle)

    ; static attributes
    (supportable blue_circle) (supportable green_circle) (supportable purple_circle) (supportable red_circle)
    (supportable large_white_circle) (dirty large_white_circle)

    (wipeable marker_scribble)
    (wet blue_water_spill)

    (deformable yellow_sponge) (graspable yellow_sponge)
    (deformable blue_sponge) (graspable blue_sponge) (wet blue_sponge)

    (graspable blue_can) (upright blue_can)
    (graspable red_can) (upright red_can))
(:goal
    ; "Clean the plate without making a mess on the table."
    (and
        (not (dirty large_white_circle))
        (not (on blue_water_spill large_white_circle))
        (not (on blue_can table_0))
        (not (on red_can table_0))
    )
)
)
