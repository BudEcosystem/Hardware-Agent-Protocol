"""Test camera stage mapping."""

import json
import os
from dataclasses import dataclass
from typing import Literal, Optional

import numpy as np
import pytest

from labthings_fastapi.testing import create_thing_without_server

from openflexure_microscope_server.things.camera.simulation import SimulatedCamera
from openflexure_microscope_server.things.camera_stage_mapping import (
    CameraStageMapper,
    CSMUncalibratedError,
    MappingError,
)
from openflexure_microscope_server.things.stage.dummy import DummyStage

from ..shared_utils.lt_test_utils import LabThingsTestEnv

RNG = np.random.default_rng()
THIS_DIR = os.path.dirname(os.path.realpath(__file__))
TEST_DATA_DIR = os.path.join(THIS_DIR, "data")


def incrementing_position_generator():
    """Generate an incrementing position."""
    i = 0
    while True:
        yield {"x": i, "y": i, "z": i}
        i += 1


@pytest.fixture
def test_env(mocker) -> LabThingsTestEnv:
    """Yield a test environment with the Simulated Camera, Dummy Stage, and CSM."""
    thing_conf = {
        "camera": SimulatedCamera,
        "stage": DummyStage,
        "camera_stage_mapping": CameraStageMapper,
    }

    position_generator = incrementing_position_generator()
    mock_pos = mocker.PropertyMock(side_effect=lambda: next(position_generator))
    mocker.patch.object(DummyStage, "position", mock_pos)

    with LabThingsTestEnv(things=thing_conf) as env:
        yield env


@pytest.fixture
def csm_in_env(test_env) -> LabThingsTestEnv:
    """Return a CameraStageMapper in the test env.

    This is useful when it need to write to disk, but limits isolation as camera and
    stage are also loaded.
    """
    return test_env.get_thing_by_type(CameraStageMapper)


def test_top_level_calibration_calls(csm_in_env, mocker):
    """Test the internal calibration functions are called by the top level action."""
    csm = csm_in_env
    # Set up to mock internal functions.
    mock_stage_pos_list = [(1, 2, 4), (8, 12, 32), (64, 128, 256)]
    mock_cam_pos_list = [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)]
    mock_csm = [[1.0, 2.0], [3.0, 4.0]]
    mock_detect_motion = mocker.patch.object(
        csm,
        "_detect_motion_on_axis",
        return_value=(mock_stage_pos_list, mock_cam_pos_list),
    )
    mock_measure_axis = mocker.patch.object(
        csm,
        "_measure_axis_displacement",
        return_value=(mock_stage_pos_list, mock_cam_pos_list),
    )
    mock_fit_csm = mocker.patch.object(
        csm, "_fit_all_csm_runs", return_value=(np.array(mock_csm), 99)
    )
    mock_fit_csm = mocker.patch.object(
        csm._cam, "grab_as_array", return_value=(np.zeros([123, 456, 3]))
    )

    # Check not calibrated.
    assert csm.image_to_stage_displacement_matrix is None
    assert csm.image_resolution is None
    assert csm.last_cal_timestamp is None
    with pytest.raises(CSMUncalibratedError):
        csm.assert_calibration()

    csm.calibrate_xy()

    # Detect motion once on each axis
    assert mock_detect_motion.call_count == 2
    # Then measure 4 times on each acis
    assert mock_measure_axis.call_count == 8
    # Measure the y axis before x
    meas_kwargs = [call.kwargs for call in mock_measure_axis.call_args_list]
    assert [kwarg["axis"] for kwarg in meas_kwargs] == ["y"] * 4 + ["x"] * 4
    # As detect motion should have returned a starting x of 1 and final of 64, and a
    # starting y of 2 and a final y of 128, we expect their motions to be 63 and 126.
    sizes = [126, -126, 126, -126, 63, -63, 63, -63]
    assert [kwarg["step_size"] for kwarg in meas_kwargs] == sizes
    assert mock_fit_csm.call_count == 1

    # Check the calibrations were saved
    assert csm.image_to_stage_displacement_matrix == mock_csm
    assert csm.image_resolution == (123, 456)
    assert csm.assert_calibration() == mock_csm

    # Read the timestamp setting and check there is a corresponding file
    timestamp = csm.last_cal_timestamp
    assert os.path.isfile(os.path.join(csm._data_dir, f"csm_data_{timestamp}.json"))
    # Load the calibration with the property
    last_cal = csm.last_calibration
    assert isinstance(last_cal, dict)
    # Check the csm and backlash can be read back
    assert last_cal["csm_matrix"] == mock_csm
    assert last_cal["backlash"] == 99


@pytest.fixture
def mocked_csm(mocker):
    """Return a CSM not connected to a server with slots mocked."""
    # Don't settle as it takes too long.
    mocker.patch(
        "openflexure_microscope_server.things.camera_stage_mapping.SETTLING_TIME", 0.0
    )
    csm = create_thing_without_server(CameraStageMapper, mock_all_slots=True)
    # Also set side effect for cam.grab_as array to return a random number
    csm._cam.grab_as_array.side_effect = lambda: RNG.normal(size=[2, 2])
    # And defined a fixed return for stage.get_xyz_position
    csm._stage.get_xyz_position.return_value = [123, 456, 789]
    csm._cam.image_is_sample.return_value = (True, "foobar")
    return csm


@pytest.fixture
def static_mock_displacement(mocker):
    """Mock displacement_between_images to always return (0, 0, 0)."""
    return mocker.patch(
        "openflexure_microscope_server.things.camera_stage_mapping."
        "displacement_between_images",
        return_value=(0, 0),
    )


def incrementing_offset_generator():
    """Generate an incrementing (x, y) offset, starting (10, 10) incrementing by 10."""
    i = 10.0
    while True:
        yield (i, i)
        i += 10.0


@pytest.fixture
def incrementing_mock_displacement(mocker):
    """Mock displacement_between_images with increasing numbers each run."""
    offset_generator = incrementing_offset_generator()
    return mocker.patch(
        "openflexure_microscope_server.things.camera_stage_mapping."
        "displacement_between_images",
        side_effect=lambda _im1, _im2: next(offset_generator),
    )


def test_failing_detect_motion_on_axis(mocked_csm, static_mock_displacement):
    """Check that detect motion fails if no motion detected."""
    csm = mocked_csm

    # As the displacement is always 0 this should run until it errors
    with pytest.raises(MappingError):
        csm._detect_motion_on_axis("x", 65)

    # Check moves are exponential
    moves = [call.kwargs["x"] for call in csm._stage.move_relative.call_args_list]
    exp_moves = [1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192, 16384]
    assert moves == exp_moves

    # Check all comparison are to the initial image at this stage.
    # Cache images from first run
    first_im = static_mock_displacement.call_args_list[0].args[0]
    second_im = static_mock_displacement.call_args_list[0].args[1]
    for call in static_mock_displacement.call_args_list[1:]:
        assert np.array_equal(call.args[0], first_im)
        assert not np.array_equal(call.args[1], second_im)
        # Update second image to check it is changing
        second_im = call.args[1]


def test_detect_motion_on_axis(mocked_csm, incrementing_mock_displacement):
    """Check that detect motion returns when expected if offset increments."""
    csm = mocked_csm

    stage_pos, cam_pos = csm._detect_motion_on_axis("x", 65)

    # Stage positions are all the values set by the mock get_xyz_position
    assert all(pos == [123, 456, 789] for pos in stage_pos)
    # There are 8 values (7 moves)
    assert len(cam_pos) == 8
    # The offsets increase until greater than 65, and the are incrementing by 10
    assert cam_pos[-1] == (70.0, 70.0)
    assert incrementing_mock_displacement.call_count == 7


def test_measure_axis_displacement(mocked_csm, incrementing_mock_displacement):
    """Check that the expected moves & calls are meade for a single axis measurement."""
    csm = mocked_csm

    stage_pos, cam_pos = csm._measure_axis_displacement("x", 123, 12)

    # For this measurement the cam pos should be cumulative
    # Cache second image from first runb
    last_image = incrementing_mock_displacement.call_args_list[0].args[1]
    for call in incrementing_mock_displacement.call_args_list[1:]:
        # First input is the image from the last run
        assert np.array_equal(call.args[0], last_image)
        # Second input is a new image
        assert not np.array_equal(call.args[1], last_image)
        # Update last image
        last_image = call.args[1]

    # Stage positions are all the values set by the mock get_xyz_position
    assert all(pos == [123, 456, 789] for pos in stage_pos)

    # There are 13 values (as we asked for 12 moves)
    assert len(cam_pos) == 13
    # The as the positions are cumulative  the generator will produce (0, 0), (10, 10),
    # (20, 20), (30, 30) ...  but the return should be (0, 0), (10, 10), (30, 30),
    # (60, 60) ...
    assert cam_pos[0] == (0.0, 0.0)
    assert cam_pos[1] == (10.0, 10.0)
    assert cam_pos[2] == (30.0, 30.0)
    assert cam_pos[3] == (60.0, 60.0)
    assert cam_pos[4] == (100.0, 100.0)
    assert cam_pos[5] == (150.0, 150.0)
    # ... skip to end.
    assert cam_pos[-1] == (780.0, 780.0)
    assert incrementing_mock_displacement.call_count == 12


@pytest.fixture
def sim_csm_data():
    """Return CSM data from a real CSM run on simulation microscope."""
    data_file = os.path.join(TEST_DATA_DIR, "real_csm_calibration.json")
    with open(data_file, "r", encoding="utf-8") as file_obj:
        return json.load(file_obj)


@pytest.fixture
def real_csm_data():
    """Return CSM data from a real CSM run on simulation microscope."""
    data_file = os.path.join(TEST_DATA_DIR, "csm_calibration.json")
    with open(data_file, "r", encoding="utf-8") as file_obj:
        return json.load(file_obj)


def test_csm_fitting(sim_csm_data, mocker):
    """Check the high level method calls the internal methods as expected."""
    csm_data = sim_csm_data
    # Don't mock the slots as we shouldn't need the camera or the stage for fitting.
    csm = create_thing_without_server(CameraStageMapper, mock_all_slots=False)

    # Fit backlash should return a different value each time.
    # 6 values, average of backlash values is 69.
    fit_backlash_return = [(88, 3), (50, 2), (100, 4), (33, 2), (99, 4), (44, 2)]
    # The above results in the following number of elements removed (0 for the first
    # in each axis as backlash isn't fitted.)
    elements_removed = [0, 3, 2, 4, 0, 2, 4, 2]

    mock_fit_backlash = mocker.patch.object(
        csm, "_fit_backlash", side_effect=fit_backlash_return
    )
    mock_fit_csm = mocker.patch.object(
        csm,
        "_fit_csm_matrix",
        return_value=np.array([[1, 2], [3, 4]]),
    )

    # Run the outer fit function.
    csm, backlash = csm._fit_all_csm_runs(csm_data)

    # Check that backlash is returened as a normal float not a numpy generic that is a
    # subclass.
    assert isinstance(backlash, float)
    assert not isinstance(backlash, np.generic)
    assert backlash == 69.0

    # Mock backlash should have been called 6 times, 3 for each axis as the first run
    # for each axis has removed backlash in the initial check for motion.
    assert mock_fit_backlash.call_count == 6

    # The matrix fit is called once
    assert mock_fit_csm.call_count == 1

    # Finally to check that the args to the matrix fit were cut due to backlash.
    # The input to the matrix fit is a list of arrays, one for each run
    stage_pos_arg = mock_fit_csm.call_args.args[0]
    cam_pos_arg = mock_fit_csm.call_args.args[1]
    assert len(stage_pos_arg) == 8
    assert len(cam_pos_arg) == 8

    for i in range(8):
        run_data = csm_data["x_run"][i] if i < 4 else csm_data["y_run"][i - 4]
        stage_data = np.array(run_data["stage_positions"])
        cam_data = np.array(run_data["cam_offsets"])

        # If backlash was called for this run
        if i not in [0, 4]:
            # Get the call correct mock call
            backlash_call = i - 1 if i < 4 else i - 2
            call = mock_fit_backlash.call_args_list[backlash_call]
            # Check the args match:
            assert call.args[0] == "x" if i < 4 else "y"
            assert np.array_equal(call.args[1], stage_data)
            assert np.array_equal(call.args[2], cam_data)

        # The expected number of positions cut from the start of each array.
        cut = elements_removed[i]
        # Each value passed to the matrix fit should be a displacement between
        # subsequent points
        rel_stage_data = stage_data[cut + 1 :, :] - stage_data[cut:-1, :]
        rel_cam_data = cam_data[cut + 1 :, :] - cam_data[cut:-1, :]

        assert np.array_equal(rel_stage_data, stage_pos_arg[i])
        assert np.array_equal(rel_cam_data, cam_pos_arg[i])


@dataclass
class BacklashTestCase:
    """The parameters to create a simulated movement run with backlash."""

    starting_pos: tuple[int, int, int] = (10, 20, 30)
    step_size: int = 150
    n_steps: int = 10
    stage_axis: Literal["x", "y"] = "x"
    ratio: float = 3.4
    parasitic_ratio: float = 0.003
    cam_axis: Literal["x", "y"] = "y"
    backlash: float = 77
    noise_level: float = 1

    expected_points_to_remove: int = 1
    error: Optional[BaseException] = None


BACKLASH_TEST_CASES = [
    # Normal data with approximately pixel level registration noise
    BacklashTestCase(),
    # Noisy data (5px)
    BacklashTestCase(noise_level=5),
    # negative steps
    BacklashTestCase(step_size=-150),
    # large backlash
    BacklashTestCase(backlash=330, expected_points_to_remove=3),
    # no backlash. 1 point is still removed as the code errs on the side of removing
    # extra points by using np.ceil
    BacklashTestCase(backlash=0, expected_points_to_remove=1),
    # other camera axis
    BacklashTestCase(cam_axis="x"),
    # Really noisy data should throw a mapping error
    BacklashTestCase(noise_level=25, error=MappingError),
]


def generate_movement_data_with_backlash(test_case: BacklashTestCase):
    """Generate data for a movement with backlash at the start of the move.

    This is done with a loop rather than numpy magic to make it easier to read and debug
    as there is no need for speed optimisation of test code that is already fast.
    """
    # Used a fixed seed so changes to the noise can't make the really noisy test
    # fail intermittently.
    rng = np.random.default_rng(0)
    start = np.array(test_case.starting_pos)
    step_size = test_case.step_size
    backlash = np.sign(step_size) * abs(test_case.backlash)
    stage_positions = []
    cam_positions = []

    # Precalculate (x,y,z) step depending on axis
    if test_case.stage_axis == "x":
        step_array = np.array([step_size, 0, 0])
    else:
        step_array = np.array([0, step_size, 0])
    # And precalculate the multiplication factor to get to camera offsets
    if test_case.cam_axis == "x":
        cam_factor = np.array([test_case.ratio, test_case.parasitic_ratio])
    else:
        cam_factor = np.array([test_case.parasitic_ratio, test_case.ratio])

    # Loop through all positions
    for i in range(test_case.n_steps + 1):
        # Set the stage displacement requested
        stage_positions.append(start + i * step_array)

        # For points below the backlash level set to 0,0
        if abs(i * test_case.step_size) <= abs(backlash):
            cam_positions.append(np.array([0, 0]))
        else:
            cam_positions.append((i * step_size - backlash) * cam_factor)

    noise = test_case.noise_level * rng.normal(size=[test_case.n_steps + 1, 2])
    return np.array(stage_positions), np.array(cam_positions) + noise


@pytest.mark.parametrize("test_case", BACKLASH_TEST_CASES)
def test_backlash_fitting(test_case):
    """Test the backlash fitting gets the correct backlash number."""
    csm = create_thing_without_server(CameraStageMapper, mock_all_slots=False)
    stage_pos, cam_pos = generate_movement_data_with_backlash(test_case)

    if test_case.error is not None:
        with pytest.raises(test_case.error):
            csm._fit_backlash("x", stage_pos, cam_pos)
        # Nothing more to check for erroring test cases
        return

    fitted_backlash, points_to_remove = csm._fit_backlash(
        test_case.stage_axis, stage_pos, cam_pos
    )

    min_backlash = test_case.backlash - 2 * test_case.noise_level
    max_backlash = test_case.backlash + 2 * test_case.noise_level
    # Check backlash is within the noise level
    assert min_backlash < fitted_backlash < max_backlash
    # Check the correct number of points to remove were identified
    assert points_to_remove == test_case.expected_points_to_remove


def test_simulation_csm_full_fit(sim_csm_data, mocker):
    """Check the full fitting works on a suimulation data run."""
    check_csm_full_fit(sim_csm_data, mocker)


def test_real_csm_full_fit(real_csm_data, mocker):
    """Check the full fitting works on a real data run."""
    check_csm_full_fit(real_csm_data, mocker)


def check_csm_full_fit(csm_data, mocker):
    """Check the full fit of the real data. This must be called from a test.

    This is largely used to test the matrix fit without creating too much fake data.
    The outer function and backlash fit are already tested above.
    """
    csm = create_thing_without_server(CameraStageMapper, mock_all_slots=False)
    # Use a mock to spy on lstsq to check the matrix fitting.
    lstsq_spy = mocker.patch(
        "openflexure_microscope_server.things.camera_stage_mapping.np.linalg.lstsq",
        wraps=np.linalg.lstsq,
    )
    fit_csm_spy = mocker.patch.object(csm, "_fit_csm_matrix", wraps=csm._fit_csm_matrix)

    csm_matrix, backlash = csm._fit_all_csm_runs(csm_data)
    assert np.array_equal(np.array(csm_data["csm_matrix"]), csm_matrix)
    assert fit_csm_spy.call_count == 1
    assert lstsq_spy.call_count == 1

    # Get the data used to call csm._fit_csm_matrix
    stage_data_in = fit_csm_spy.call_args.args[0]
    cam_data_in = fit_csm_spy.call_args.args[1]

    # Check it is a list of arrays
    assert isinstance(stage_data_in, list)
    assert isinstance(stage_data_in[0], np.ndarray)
    assert stage_data_in[0].shape == (10, 3)
    assert isinstance(cam_data_in, list)
    assert isinstance(cam_data_in[0], np.ndarray)
    assert cam_data_in[0].shape == (10, 2)

    # Check that when sent to lslsq it is all concatenated
    stage_data_for_lslsq = lstsq_spy.call_args.args[1]
    cam_data_for_lslsq = lstsq_spy.call_args.args[0]

    # Check nothing else sent to np.lslsq
    assert len(lstsq_spy.call_args.args) == 2
    assert lstsq_spy.call_args.kwargs == {}

    # check shape
    assert stage_data_for_lslsq.shape == (74, 2)
    assert cam_data_for_lslsq.shape == (74, 2)

    # And the at the start of the data matches.
    assert np.array_equal(stage_data_in[0][:, :2], stage_data_for_lslsq[:10, :])
    assert np.array_equal(cam_data_in[0], cam_data_for_lslsq[:10, :])

    # Used a fixed seed so changes to the noise can't make the really noisy test
    # fail intermittently.
    rng = np.random.default_rng(0)
    # Finally check that the matrix fit throws a MappingError if the data is really
    # noisy
    noisy_cam_data = [data + 15 * rng.normal(size=data.shape) for data in cam_data_in]

    with pytest.raises(MappingError):
        csm._fit_csm_matrix(stage_data_in, noisy_cam_data)
