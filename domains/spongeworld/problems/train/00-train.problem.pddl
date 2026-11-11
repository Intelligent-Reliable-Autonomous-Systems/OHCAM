(define (problem spongeworld-train-00)
(:domain spongeworld)
(:objects table_0 - table
    yellow_sponge blue_sponge - sponge
    blue_water_spill marker_scribble - spill
    blue_can - can
    white_plate - plate
    purple_circle green_circle red_circle - target)
(:init
    (on red_circle table_0)
    (on green_circle table_0)
    (on purple_circle table_0)
    (on white_plate table_0)
    (on marker_scribble white_plate)
    (on yellow_sponge green_circle)
    (on blue_sponge red_circle)
    (on blue_can purple_circle)
    (obstructed green_circle)
    (obstructed red_circle)
    (obstructed purple_circle)
    (dirty white_plate)

    ; item static attributes
    (graspable yellow_sponge)
    (deformable yellow_sponge)
    (deformable blue_sponge)
    (graspable blue_sponge)
    (graspable blue_can)
    (wet blue_sponge)
    (upright blue_can)
    (supportable red_circle)
    (supportable green_circle)
    (supportable purple_circle)
    (supportable white_plate)
    (wipeable marker_scribble)
    (wet blue_water_spill)
)
(:goal
    (and
        (on red_circle purple_circle) ; impossible goal for exploratio
    )
)
)
