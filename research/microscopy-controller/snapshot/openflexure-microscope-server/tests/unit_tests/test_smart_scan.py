"""Test the SmartScanThing *without* connecting it to a LabThings Server.

By testing without connecting to the LabThings server it is possible to
directly poll any properties and to start any methods.

Any methods with LabThings dependency injections will require dependencies
to be passed in manually. Rather than passing in real LabThings clients
it is possible to create test objects that mock these clients. Thus, entirely
isolating one Thing for testing, at the expense of needing to create detailed
mock objects.

For these tests to reliably represent real behaviour the mock Things will need to
be tested for matching signatures with dynamically generated clients.
"""

import logging
import os
import re
import tempfile
import time
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from unittest import mock

import pytest
from fastapi import HTTPException
from pydantic import BaseModel, ValidationError

from labthings_fastapi.exceptions import InvocationCancelledError
from labthings_fastapi.testing import create_thing_without_server

from openflexure_microscope_server import ui
from openflexure_microscope_server.scan_directories import (
    ScanDirectory,
    ScanGalleryDBEngine,
)
from openflexure_microscope_server.stitching import StitchingSettings
from openflexure_microscope_server.things.scan_workflows import ScanWorkflow
from openflexure_microscope_server.things.smart_scan import (
    ActiveScanData,
    LiveScanDetails,
    ScanNotRunningError,
    SmartScanThing,
)
from openflexure_microscope_server.utilities import NotEnoughFreeSpaceError


@pytest.fixture
def entered_smart_scan_thing(smart_scan_thing):
    """Yield a smart scan thing as a fixture that has been entred.

    This will make a scan directory manager. This fixture also clears the scan dir
    """
    with smart_scan_thing:
        yield smart_scan_thing


def custom_smart_scan_thing(default_workflow, all_workflows, mocker):
    """Set up a custom smart scan thing with workflows adjusted.

    This allows setting a default workflow and to adjust all workflows from simple
    single item mock from `mock_all_slots`.
    """
    smart_scan_thing = create_thing_without_server(
        SmartScanThing,
        default_workflow=default_workflow,
        mock_all_slots=True,
    )
    interface_type = type(smart_scan_thing._thing_server_interface)
    interface_type.application_config = mocker.PropertyMock(
        return_value={"data_folder": tempfile.gettempdir()}
    )
    # Pop the existing mock workflow and add specified ones (if any)
    smart_scan_thing._all_workflows.pop("mock-_all_workflows")
    for key, thing in all_workflows.items():
        smart_scan_thing._all_workflows[key] = thing

    return smart_scan_thing


def test_initial_properties(entered_smart_scan_thing):
    """Check the initial values of properties.

    Test properties of SmartScanThing are available without a ThingServer
    and return expected default values.
    """
    smart_scan_thing = entered_smart_scan_thing
    assert isinstance(smart_scan_thing._gallery_db_engine, ScanGalleryDBEngine)
    assert smart_scan_thing._gallery_db_engine._data_dir == smart_scan_thing.data_dir
    assert smart_scan_thing.latest_scan_live_details is None


@dataclass
class WorkflowSelectorTestCase:
    """The information needed to test the workflow selector."""

    workflows: dict[str, mock.MagicMock]
    default_wf: str
    expected_wf: Optional[str]
    loaded_wf: Optional[str] = None
    side_effect: Optional[type | int | Iterable[int]] = None
    """The side effect of entering the Thing (None, Logger level number, Error type)"""
    match: Optional[str | Iterable[str]] = None


SELECTOR_CASES = [
    WorkflowSelectorTestCase(
        workflows={},
        default_wf="foo",
        expected_wf=None,
        side_effect=RuntimeError,
        match="Could not set Scan Workflow",
    ),
    WorkflowSelectorTestCase(
        workflows={
            "foo": mock.MagicMock(spec=ScanWorkflow),
            "bar": mock.MagicMock(spec=ScanWorkflow),
        },
        default_wf="foo",
        expected_wf="foo",
        side_effect=None,
    ),
    WorkflowSelectorTestCase(
        workflows={
            "foo": mock.MagicMock(spec=ScanWorkflow),
            "bar": mock.MagicMock(spec=ScanWorkflow),
        },
        default_wf="bar",
        expected_wf="bar",
        side_effect=None,
    ),
    WorkflowSelectorTestCase(
        workflows={
            "foo": mock.MagicMock(spec=ScanWorkflow),
            "bar": mock.MagicMock(spec=ScanWorkflow),
        },
        default_wf="wrong",
        expected_wf="foo",
        side_effect=logging.WARNING,
        match="Could not select default key 'wrong'",
    ),
    WorkflowSelectorTestCase(
        workflows={
            "foo": mock.MagicMock(spec=ScanWorkflow),
            "bar": mock.MagicMock(spec=ScanWorkflow),
        },
        default_wf="wrong",
        loaded_wf="bar",
        expected_wf="bar",
        side_effect=None,
    ),
    WorkflowSelectorTestCase(
        workflows={
            "foo": mock.MagicMock(spec=ScanWorkflow),
            "bar": mock.MagicMock(spec=ScanWorkflow),
        },
        default_wf="wrong",
        loaded_wf="wrong",
        expected_wf="foo",
        side_effect=[logging.WARNING, logging.WARNING],
        match=[
            "Could not select 'wrong' from Thing mapping",
            "Could not select default key 'wrong'",
        ],
    ),
]


@pytest.mark.parametrize("case", SELECTOR_CASES)
def test_workflow_set_on_enter(case, check_side_effect, mocker):
    """Check workflow is set on enter."""
    smart_scan_thing = custom_smart_scan_thing(case.default_wf, case.workflows, mocker)
    with check_side_effect(case.side_effect, match=case.match):
        # Load in "loaded" as the sever would
        smart_scan_thing._workflow_name = case.loaded_wf
        with smart_scan_thing:
            assert smart_scan_thing._workflow_name == case.expected_wf
    # If there was an exception during `__enter__` the database isn't cleaned
    # as __exit__ is never run so manually clean up to stop state leaking to other
    # tests.
    if isinstance(case.side_effect, type(Exception)):
        smart_scan_thing._gallery_db_engine.dispose()


def test_setting_workflows(caplog, mocker):
    """Check that setting workflow works, or warns if incorrect."""
    workflows = {
        "foo": mock.MagicMock(spec=ScanWorkflow),
        "bar": mock.MagicMock(spec=ScanWorkflow),
    }
    smart_scan_thing = custom_smart_scan_thing("foo", workflows, mocker)
    with caplog.at_level(logging.WARNING), smart_scan_thing:
        assert smart_scan_thing._workflow_name == "foo"
        assert smart_scan_thing._workflow is workflows["foo"]
        # Can't set None, raises a ValidationError
        with pytest.raises(ValidationError):
            smart_scan_thing.workflow_name = None
        # Empty string still won't change, but just warns
        smart_scan_thing.workflow_name = ""
        assert len(caplog.records) == 1
        assert smart_scan_thing._workflow_name == "foo"
        assert smart_scan_thing._workflow is workflows["foo"]
        # Can't set a different name
        smart_scan_thing.workflow_name = "wrong"
        assert len(caplog.records) == 2  # another log
        assert smart_scan_thing._workflow_name == "foo"
        assert smart_scan_thing._workflow is workflows["foo"]

        # can set a valid name
        smart_scan_thing.workflow_name = "bar"
        assert len(caplog.records) == 2  # No extra logs
        assert smart_scan_thing._workflow_name == "bar"
        assert smart_scan_thing._workflow is workflows["bar"]


def test_gallery_db_error_if_unstarted(smart_scan_thing):
    """Check error raised if accessing gallery engine before server starts."""
    # Errors if unstarted:
    with pytest.raises(RuntimeError, match="Gallery engine has not been created yet."):
        smart_scan_thing.gallery_db_engine
    # Enter the thing, simulating the server starting:
    with smart_scan_thing:
        assert isinstance(smart_scan_thing.gallery_db_engine, ScanGalleryDBEngine)


def test_gallery_bulk_actions(smart_scan_thing):
    """Check the only gallery bulk action is stitch all scans."""
    action_buttons = smart_scan_thing.get_gallery_bulk_actions()
    assert len(action_buttons) == 1
    button = action_buttons[0]
    assert isinstance(button, ui.ActionButton)
    assert button.thing == smart_scan_thing.name
    assert button.action == "stitch_all_scans"
    assert button.submit_label == "Stitch All Unstitched Scans"
    assert button.can_terminate
    assert not button.button_primary
    assert button.modal_progress
    assert button.requires_confirmation


def test_inaccessible_scan_methods(smart_scan_thing):
    """Test that method with @_scan_running decorator is inaccessible.

    The @_scan_running decorator makes these functions inaccessible unless
    a scan is running. Also test properties that raise same error.
    """
    with pytest.raises(ScanNotRunningError):
        smart_scan_thing._run_scan()
    with pytest.raises(ScanNotRunningError):
        smart_scan_thing._manage_stitching_threads()

    # Properties
    with pytest.raises(ScanNotRunningError):
        smart_scan_thing.scan_data
    with pytest.raises(ScanNotRunningError):
        smart_scan_thing.ongoing_scan


def test_private_delete_scan(entered_smart_scan_thing, caplog):
    """Test the private _delete_scan method deletes directories or warns if it can't."""
    smart_scan_thing = entered_smart_scan_thing
    scan_dir = smart_scan_thing.data_dir
    with caplog.at_level(logging.INFO):
        fake_scan_name = "fake_scan_0001"
        fake_scan_path = os.path.join(scan_dir, fake_scan_name)

        # Attempt to delete the fake scan. Expect it to fail and provide a warning
        deleted = smart_scan_thing._delete_scan(fake_scan_name)
        assert not deleted
        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == "WARNING"
        assert caplog.records[0].name == "labthings_fastapi.things.smartscanthing"

        # Make a dir for the fake scan and delete it.
        os.makedirs(fake_scan_path)
        smart_scan_thing.gallery_db_engine.add(fake_scan_name)
        assert os.path.exists(fake_scan_path)
        assert fake_scan_name in smart_scan_thing.gallery_db_engine.get_all_paths()
        deleted = smart_scan_thing._delete_scan(fake_scan_name)
        assert not os.path.exists(fake_scan_path)
        assert deleted
        # Check no extra logs generated
        assert len(caplog.records) == 1


def test_public_delete_scan(entered_smart_scan_thing, caplog):
    """Test the delete_scan API call deletes directories or warns if it can't."""
    smart_scan_thing = entered_smart_scan_thing
    scan_dir = smart_scan_thing.data_dir
    with caplog.at_level(logging.INFO):
        fake_scan_name = "fake_scan_0001"
        fake_scan_path = os.path.join(scan_dir, fake_scan_name)

        # Attempt to delete the fake scan. Expect it to fail
    with pytest.raises(HTTPException) as exc_info:
        smart_scan_thing.delete_scan(fake_scan_name)
    # Should raise a 400 error if the scan doesn't exist, not a 404 as the server
    # was not expecting to receive the scan files
    assert exc_info.value.status_code == 400
    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == "WARNING"
    assert caplog.records[0].name == "labthings_fastapi.things.smartscanthing"

    # Make a dir for the fake scan and delete it.
    os.makedirs(fake_scan_path)
    smart_scan_thing.gallery_db_engine.add(fake_scan_name)
    assert os.path.exists(fake_scan_path)
    assert fake_scan_name in smart_scan_thing.gallery_db_engine.get_all_paths()

    smart_scan_thing.delete_scan(fake_scan_name)
    assert not os.path.exists(fake_scan_path)
    # Check no extra logs generated
    assert len(caplog.records) == 1


def test_delete_all_scans(entered_smart_scan_thing, caplog, mocker):
    """Check the delete_all_scan API really does delete all the scans."""
    mock_raise_if_cancelled = mocker.patch(
        "openflexure_microscope_server.things.smart_scan.lt.raise_if_cancelled",
    )
    smart_scan_thing = entered_smart_scan_thing
    scan_dir = smart_scan_thing.data_dir
    with caplog.at_level(logging.INFO):
        fake_scan_names = [
            "fake_scan_0001",
            "fake_scan_0002",
            "fake_scan_0003",
            "fake_scan_0004",
        ]
        for fake_scan_name in fake_scan_names:
            fake_scan_path = os.path.join(scan_dir, fake_scan_name)
            os.makedirs(fake_scan_path)
            assert os.path.exists(fake_scan_path)

        # Updated the database as the scans were mad without adding.
        smart_scan_thing.gallery_db_engine.sync_db_with_file_system()

        # Now delete them all
        smart_scan_thing.delete_all_gallery_items()
        for fake_scan_name in fake_scan_names:
            fake_scan_path = os.path.join(scan_dir, fake_scan_name)
            assert not os.path.exists(fake_scan_path)
        # One log generated per scan deleted
        assert len(caplog.records) == 4
        for record in caplog.records:
            assert record.message.startswith("Deleting: fake_scan_000")
            assert record.levelname == "INFO"
        # Check that raise_if_cancelled is called once for each scan.
        assert mock_raise_if_cancelled.call_count == 4


def test_get_scan_dir(entered_smart_scan_thing):
    """Check getting the scan dir returns a ScanDirectory only if the dir exists."""
    smart_scan_thing = entered_smart_scan_thing

    # Error raised if the directory doesn't exist.
    with pytest.raises(FileNotFoundError):
        smart_scan_thing._get_scan_dir("foo")

    # Make a directory in the smart scan data dir
    os.makedirs(os.path.join(smart_scan_thing.data_dir, "foo"))
    # Now _get_scan_dir doesn't error
    scan_dir = smart_scan_thing._get_scan_dir("foo")
    assert isinstance(scan_dir, ScanDirectory)
    assert scan_dir.name == "foo"


def test_workflows_found(simulation_test_env):
    """Check all workflow in the simulation test env are found."""
    env = simulation_test_env
    thing = env.get_thing_by_type(SmartScanThing)
    assert thing.all_workflow_names == [
        "histo_scan_workflow",
        "snake_workflow",
        "raster_workflow",
    ]
    assert thing.workflow_display_names == {
        "histo_scan_workflow": "Histo Scan",
        "snake_workflow": "Snake Scan",
        "raster_workflow": "Raster Scan",
    }


MOCK_SCAN_NAME = "testcase_id_0001"
MOCK_SCAN_DIR = "scans/testcase_id_0001/images/"
MOCK_START_POS = {"x": 123, "y": 456, "z": 789}


class MockWorkflowSettingModel(BaseModel):
    """A mock model to check that ActiveScanData can hold arbitrary models."""

    foo: str = "bar"
    bar: str = "foo"
    dx: int = 123
    dy: int = 456


def _expected_scan_data(image_count=0):
    """Return the expected ActiveScanData object for a SmartScan with default properties."""
    expected_dict = {
        "scan_name": MOCK_SCAN_NAME,
        "starting_position": MOCK_START_POS,
        "save_resolution": (1640, 1232),
        "stitch_automatically": True,
        "stitching_settings": {
            "overlap": 0.35,
            "correlation_resize": 0.5,
        },
        "workflow": "Mock",
        "workflow_settings": MockWorkflowSettingModel(),
    }
    return ActiveScanData(
        start_time=datetime.now(),
        start_monotonic=time.monotonic(),
        image_count=image_count,
        **expected_dict,
    )


def test_scan_will_not_start_if_locked(entered_smart_scan_thing):
    """Test the scan lock."""
    # It isn't an R lock so no need for a thread.
    entered_smart_scan_thing._scan_lock.acquire()
    with pytest.raises(
        RuntimeError, match="Trying to run scan while scan is already running!"
    ):
        entered_smart_scan_thing.sample_scan()
    entered_smart_scan_thing._scan_lock.release()


@dataclass
class ScanSetupTeardownTestCase:
    """The information needed to test starting up a scan and cleaning up afterwards."""

    testcase_id: str
    workflow_check_exception: Optional[Exception]
    run_scan_exception: Optional[Exception]
    workflow_check_exception: Optional[type[Exception]]
    run_scan_exception: Optional[type[Exception]]
    scan_data_set_by_run: Optional[ActiveScanData]
    expected_final_scan_data: Optional[ActiveScanData]
    scan_log_writes: int
    uncaught_exception_type: Optional[type[Exception]]
    return_to_start_called: bool = False
    """If return to centre is called by the outer action code not the main run_scan.

    This only happens if there is an exception, which is not a cancelled exception.
    """


EXAMPLE_SCAN_DATA = _expected_scan_data()
EXAMPLE_SCAN_DATA_W_1_IMG = _expected_scan_data(image_count=1)
EXAMPLE_SCAN_DATA_W_10_IMGS = _expected_scan_data(image_count=10)

SCAN_SETUP_TEARDOWN_TEST_CASES = [
    ScanSetupTeardownTestCase(
        testcase_id="Failed to setup scan, no log is written.",
        workflow_check_exception=RuntimeError,
        run_scan_exception=None,
        scan_data_set_by_run=deepcopy(EXAMPLE_SCAN_DATA),
        expected_final_scan_data=None,  # Scan never ran, so no scan data
        scan_log_writes=0,  # No directory created, so no log written
        uncaught_exception_type=RuntimeError,
    ),
    ScanSetupTeardownTestCase(
        testcase_id="Normal working scan",
        workflow_check_exception=None,
        run_scan_exception=None,
        scan_data_set_by_run=deepcopy(EXAMPLE_SCAN_DATA),
        expected_final_scan_data=deepcopy(EXAMPLE_SCAN_DATA),
        scan_log_writes=1,  # Once at end, all others would be in run_scan
        uncaught_exception_type=None,
    ),
    ScanSetupTeardownTestCase(
        testcase_id="Normal working scan that was cancelled during running",
        workflow_check_exception=None,
        run_scan_exception=InvocationCancelledError,
        scan_data_set_by_run=deepcopy(EXAMPLE_SCAN_DATA),
        expected_final_scan_data=deepcopy(EXAMPLE_SCAN_DATA),
        scan_log_writes=1,  # Once at end, all others would be in run_scan
        uncaught_exception_type=InvocationCancelledError,
    ),
    ScanSetupTeardownTestCase(
        testcase_id="Normal working scan that was cancelled before scan data set",
        workflow_check_exception=None,
        run_scan_exception=InvocationCancelledError,
        scan_data_set_by_run=None,
        expected_final_scan_data=None,
        scan_log_writes=1,  # Once error handling, all others in log_scan
        uncaught_exception_type=InvocationCancelledError,
    ),
    ScanSetupTeardownTestCase(
        testcase_id="Scan has runtime error after scan data is created",
        workflow_check_exception=None,
        run_scan_exception=RuntimeError,
        scan_data_set_by_run=deepcopy(EXAMPLE_SCAN_DATA),
        expected_final_scan_data=deepcopy(EXAMPLE_SCAN_DATA),
        scan_log_writes=1,  # Once error handling, all others in log_scan
        uncaught_exception_type=RuntimeError,
        return_to_start_called=True,  # The only time this is true
    ),
    ScanSetupTeardownTestCase(
        testcase_id="Scan has runtime error before scan data is created",
        workflow_check_exception=None,
        run_scan_exception=RuntimeError,
        scan_data_set_by_run=None,
        expected_final_scan_data=None,
        scan_log_writes=1,  # Once error handling, all others in log_scan
        uncaught_exception_type=RuntimeError,
    ),
]


@pytest.mark.parametrize(
    "testcase",
    SCAN_SETUP_TEARDOWN_TEST_CASES,
    ids=lambda testcase: testcase.testcase_id,
)
def test_scan_setup_and_teardown(
    testcase,
    entered_smart_scan_thing,
    mocker,
):
    """Run the sample scan action mocking run_scan to test scan setup and teardown."""
    smart_scan_thing = entered_smart_scan_thing

    # Functions for mocks to call:
    def check_workflow(*_args, **_kwargs):
        """Replace the workflow check.

        This raises the exception set in the test case if any. But first always
        checks that the scan is locked.
        """
        assert smart_scan_thing._scan_lock.locked()
        if testcase.workflow_check_exception is not None:
            raise testcase.workflow_check_exception

    def check_data(*_args, **_kwargs):
        assert smart_scan_thing._scan_data == testcase.expected_final_scan_data

    def mocked_run(*_args, **_kwargs):
        """Set scan_data and raise exception if requested."""
        smart_scan_thing._scan_data = testcase.scan_data_set_by_run
        if testcase.run_scan_exception is not None:
            raise testcase.run_scan_exception

    # Set up a lot of mocks!!
    smart_scan_thing._workflow.check_before_start.side_effect = check_workflow

    mocker.patch.object(
        smart_scan_thing.gallery_db_engine,
        "unique_scan_name",
        return_value=MOCK_SCAN_NAME,
    )
    ongoing_scan_mock = mocker.Mock()
    ongoing_scan_mock.name = MOCK_SCAN_NAME

    mocker.patch(
        "openflexure_microscope_server.scan_directories.ScanDirectory.new_scan_dir",
        return_value=ongoing_scan_mock,
    )
    mocker.patch.object(smart_scan_thing, "_run_scan", side_effect=mocked_run)
    # This is used to check the scan data that reaches the finally
    mocker.patch.object(
        smart_scan_thing, "_set_final_details_add_to_db", side_effect=check_data
    )
    mocker.patch.object(smart_scan_thing, "purge_empty_scans")
    mocker.patch.object(smart_scan_thing, "_return_to_starting_position")

    # Run the action
    if testcase.uncaught_exception_type is None:
        smart_scan_thing.sample_scan(scan_name="FooBar")
    else:
        with pytest.raises(testcase.uncaught_exception_type):
            smart_scan_thing.sample_scan(scan_name="FooBar")

    # Perform testcase checks
    assert ongoing_scan_mock.save_scan_log.call_count == testcase.scan_log_writes

    assert smart_scan_thing._return_to_starting_position.call_count == int(
        testcase.return_to_start_called
    )

    # Check the things that are released in the finally block are always released.
    assert not smart_scan_thing._scan_lock.locked()
    assert smart_scan_thing._ongoing_scan is None
    assert smart_scan_thing._scan_data is None
    assert smart_scan_thing._preview_stitcher is None

    # check the two functions that always run:
    assert smart_scan_thing._set_final_details_add_to_db.call_count == 1
    assert smart_scan_thing.purge_empty_scans.call_count == 1


def test_live_scan_details(entered_smart_scan_thing, mocker):
    """Check the expected live scan details are returned."""
    smart_scan_thing = entered_smart_scan_thing
    # Starts as None
    assert smart_scan_thing.latest_scan_live_details is None

    # Create a LiveScanDetails object
    details = LiveScanDetails(name=MOCK_SCAN_NAME)

    # check that the 3 attrs we expect to change start as expected
    assert details.image_count == 0
    assert details.duration_seconds is None
    assert details.stitch_timestamp is None

    # Make an unchanging copy
    original_details = deepcopy(details)

    # And set to private attr
    smart_scan_thing._latest_scan_live_details = details
    # It should be returned unchanged if there is no scan data
    details_read = smart_scan_thing.latest_scan_live_details
    assert details_read is details
    assert details_read == original_details

    # Set some scan data
    smart_scan_thing._scan_data = _expected_scan_data()
    # And set an image count
    smart_scan_thing._scan_data.image_count = 12

    # Read details again
    details_read = smart_scan_thing.latest_scan_live_details

    # Check that the image count is set as expected
    assert details_read.image_count == 12
    # check there is a time that is greater than 0s
    assert details_read.duration_seconds > 0
    # Check nothing else changed by only setting the values we know
    current_details = deepcopy(original_details)
    current_details.image_count = 12
    current_details.duration_seconds = details_read.duration_seconds
    assert details_read == current_details

    # Finally mock the preview stitch time for the last parameter that can change
    mocker.patch.object(
        type(smart_scan_thing),
        "latest_preview_stitch_time",
        mocker.PropertyMock(return_value=123),
        create=True,
    )
    # And increase the image count
    smart_scan_thing._scan_data.image_count = 14

    # Read details one last time
    details_read = smart_scan_thing.latest_scan_live_details

    assert details_read.image_count == 14
    # check the time increased
    assert details_read.duration_seconds > current_details.duration_seconds
    # The timestamp is the mocked value
    assert details_read.stitch_timestamp == 123
    # Again, check that nothing else changed by only setting the values we know
    current_details = deepcopy(original_details)
    current_details.image_count = 14
    current_details.duration_seconds = details_read.duration_seconds
    current_details.stitch_timestamp = 123
    assert details_read == current_details


@dataclass
class FinalDetailsAndDBTestCase:
    """The information needed to test final update of live details and adding to the database."""

    testcase_id: str
    starting_live_scan_details: Optional[LiveScanDetails]
    scan_data: Optional[ActiveScanData]
    preview_stitcher_created: bool
    final_live_scan_details: Optional[LiveScanDetails]
    """Note duration is always mocked to 123 on the final update in the test."""
    final_duration_set: bool
    added_to_db: bool


FINAL_DETAILS_AND_DB_TEST_CASES = [
    # A scan that stopped before anything was set
    FinalDetailsAndDBTestCase(
        testcase_id="A scan that stopped before anything was set",
        starting_live_scan_details=None,
        scan_data=None,
        preview_stitcher_created=False,
        final_live_scan_details=None,
        final_duration_set=False,
        added_to_db=False,
    ),
    FinalDetailsAndDBTestCase(
        testcase_id="A scan that stopped after 1 image",
        starting_live_scan_details=LiveScanDetails(name="foo"),
        scan_data=deepcopy(EXAMPLE_SCAN_DATA_W_1_IMG),
        preview_stitcher_created=False,
        final_live_scan_details=LiveScanDetails(
            name="foo", image_count=1, scan_phase="Complete", duration_seconds=123
        ),
        final_duration_set=True,
        added_to_db=True,
    ),
    FinalDetailsAndDBTestCase(
        testcase_id="A scan that stopped after 10 images",
        starting_live_scan_details=LiveScanDetails(name="foo"),
        scan_data=deepcopy(EXAMPLE_SCAN_DATA_W_10_IMGS),
        preview_stitcher_created=True,
        final_live_scan_details=LiveScanDetails(
            name="foo",
            image_count=10,
            scan_phase="Complete",
            duration_seconds=123,
            stitch_timestamp=456,
        ),
        final_duration_set=True,
        added_to_db=True,
    ),
]


@pytest.mark.parametrize(
    "testcase",
    FINAL_DETAILS_AND_DB_TEST_CASES,
    ids=lambda testcase: testcase.testcase_id,
)
def test_final_details_and_add_to_db(testcase, entered_smart_scan_thing, mocker):
    """Check adding final details and adding to database logic matches each testcase."""
    smart_scan_thing = entered_smart_scan_thing

    # Set initial values
    smart_scan_thing._latest_scan_live_details = testcase.starting_live_scan_details
    smart_scan_thing._scan_data = testcase.scan_data
    smart_scan_thing._preview_stitcher = (
        mocker.Mock() if testcase.preview_stitcher_created else None
    )

    # And mock the duration update so it can be tested if it runs easily.
    def mock_update_duration(self, _start_time):
        """Mock the duration update."""
        self.duration_seconds = 123

    duration_mock = mocker.patch.object(
        LiveScanDetails,
        "update_duration",
        side_effect=mock_update_duration,
        autospec=True,
    )
    # And mock the preview stitch time
    mocker.patch.object(
        type(smart_scan_thing),
        "latest_preview_stitch_time",
        mocker.PropertyMock(return_value=456),
        create=True,
    )

    # Also mock adding to the database
    add_mock = mocker.patch.object(smart_scan_thing.gallery_db_engine, "add")

    smart_scan_thing._set_final_details_add_to_db()

    assert duration_mock.call_count == int(testcase.final_duration_set)
    assert add_mock.call_count == int(testcase.added_to_db)

    expected_details = deepcopy(testcase.final_live_scan_details)
    if testcase.final_duration_set:
        assert smart_scan_thing._latest_scan_live_details.duration_seconds == 123

    assert smart_scan_thing._latest_scan_live_details == expected_details


@pytest.fixture
def scan_thing_mocked_for_scan_data(smart_scan_thing, mocker):
    """Return a scan thing that is mocked so that _collect_scan_data will run."""
    # Set the lock so it thinks the scan is running
    with smart_scan_thing._scan_lock:
        smart_scan_thing._stage.position = MOCK_START_POS

        smart_scan_thing._workflow.all_settings.return_value = (
            MockWorkflowSettingModel(),
            StitchingSettings(correlation_resize=0.5, overlap=0.35),
            (1640, 1232),
        )

        mock_ongoing_scan = mocker.Mock()
        mock_ongoing_scan.name = MOCK_SCAN_NAME
        mock_ongoing_scan.images_dir = MOCK_SCAN_DIR
        smart_scan_thing._ongoing_scan = mock_ongoing_scan
        smart_scan_thing._data_dir = "scans"

        yield smart_scan_thing


def test_collect_scan_data(scan_thing_mocked_for_scan_data):
    """Run _collect_scan_data, and check the ActiveScanData object has the expected values."""
    scan_thing = scan_thing_mocked_for_scan_data

    data = scan_thing._collect_scan_data(scan_thing._workflow)
    expected_data = _expected_scan_data()
    time_diff = expected_data.start_time - data.start_time
    assert abs(time_diff.total_seconds()) < 1
    mono_time_diff = expected_data.start_monotonic - data.start_monotonic
    assert abs(mono_time_diff) < 1
    # Set times to exactly the same before final comparison
    expected_data.start_time = data.start_time
    expected_data.start_monotonic = data.start_monotonic
    assert data == expected_data


def test_save_final_scan_data(scan_thing_mocked_for_scan_data):
    """Run _save_final_scan_data, check save is called with final results in ActiveScanData."""
    scan_thing = scan_thing_mocked_for_scan_data

    scan_thing._scan_data = scan_thing._collect_scan_data(scan_thing._workflow)
    scan_thing._scan_data.image_count = 44
    scan_thing._save_final_scan_data("Mocked!")
    # _ongoing_scan is a mock so we can check that save_scan data was called and get
    # the value
    scan_thing._ongoing_scan.save_scan_data.assert_called()
    final_data = scan_thing._ongoing_scan.save_scan_data.call_args[0][0]
    assert isinstance(final_data, ActiveScanData)
    assert final_data.scan_result == "Mocked!"
    assert final_data.image_count == 44
    assert final_data.duration.total_seconds() < 1


@pytest.fixture
def scan_thing_mocked_for_run_scan(scan_thing_mocked_for_scan_data, mocker):
    """Return a scan_thing mocked so _run_scan works.

    main_scan_loop(), _return_to_starting_position(), and _perform_final_stitch() are
    Mocks and _cam is a MockCameraThing
    """
    scan_thing = scan_thing_mocked_for_scan_data
    mocker.patch.object(scan_thing, "_main_scan_loop")
    mocker.patch.object(scan_thing, "_return_to_starting_position")
    mocker.patch.object(scan_thing, "_perform_final_stitch")
    scan_thing._latest_scan_live_details = LiveScanDetails(
        name=scan_thing.ongoing_scan.name
    )

    return scan_thing


@dataclass
class RunScanTestCase:
    """The expected behaviour when running run scan with main loop mocked."""

    testcase_id: str
    expected_exception: Optional[type[Exception]]
    expected_scan_result: str
    expected_log_levels: list[int]
    cam_change_streaming_mode_calls: int
    main_scan_loop_calls: int
    return_to_start_calls: int
    perform_final_stitch_calls: int
    save_scan_data_calls: int


RUN_SCAN_TEST_CASES = [
    RunScanTestCase(
        testcase_id="scan completes successfully",
        expected_exception=None,
        expected_scan_result=r"^success$",
        expected_log_levels=[],
        cam_change_streaming_mode_calls=2,
        main_scan_loop_calls=1,
        return_to_start_calls=1,
        perform_final_stitch_calls=1,
        save_scan_data_calls=2,
    ),
    RunScanTestCase(
        testcase_id="main loop raises FileNotFoundError",
        expected_exception=FileNotFoundError,
        expected_scan_result=r"^FileNotFoundError: .*$",
        expected_log_levels=[logging.ERROR],
        cam_change_streaming_mode_calls=2,
        main_scan_loop_calls=1,
        return_to_start_calls=0,
        perform_final_stitch_calls=0,
        save_scan_data_calls=2,
    ),
    RunScanTestCase(
        testcase_id="scan is cancelled",
        expected_exception=InvocationCancelledError,
        expected_scan_result=r"^cancelled by user$",
        expected_log_levels=[],
        cam_change_streaming_mode_calls=2,
        main_scan_loop_calls=1,
        return_to_start_calls=1,
        perform_final_stitch_calls=0,
        save_scan_data_calls=2,
    ),
    RunScanTestCase(
        testcase_id="disk fills up",
        expected_exception=NotEnoughFreeSpaceError,
        expected_scan_result=r"^NotEnoughFreeSpaceError: .*$",
        expected_log_levels=[logging.ERROR],
        cam_change_streaming_mode_calls=2,
        main_scan_loop_calls=1,
        return_to_start_calls=0,
        perform_final_stitch_calls=0,
        save_scan_data_calls=2,
    ),
]


@pytest.mark.parametrize(
    "testcase",
    RUN_SCAN_TEST_CASES,
    ids=lambda testcase: testcase.testcase_id,
)
def test_run_scan(testcase, scan_thing_mocked_for_run_scan, caplog, mocker):
    """Check _run_scan behaviour against each testcase."""
    scan_thing = scan_thing_mocked_for_run_scan

    if testcase.expected_exception is not None:
        mocker.patch.object(
            scan_thing,
            "_main_scan_loop",
            side_effect=testcase.expected_exception("mocked"),
        )

    with caplog.at_level(logging.WARNING):
        if testcase.expected_exception is None:
            scan_thing._scan_data = scan_thing._run_scan(scan_thing._workflow)
        else:
            with pytest.raises(testcase.expected_exception):
                scan_thing._scan_data = scan_thing._run_scan(scan_thing._workflow)

    # The preview stitcher object should still exist and the images dir should be set.
    assert scan_thing._preview_stitcher.images_dir == MOCK_SCAN_DIR

    final_scan_data = scan_thing._ongoing_scan.save_scan_data.call_args[0][0]

    assert re.fullmatch(testcase.expected_scan_result, final_scan_data.scan_result)

    # Use strict = True so an error is raised if the number of logs is wrong.
    for record, level in zip(caplog.records, testcase.expected_log_levels, strict=True):
        assert record.levelno == level

    assert scan_thing._cam.change_streaming_mode.call_count == (
        testcase.cam_change_streaming_mode_calls
    )
    assert scan_thing._main_scan_loop.call_count == testcase.main_scan_loop_calls
    assert scan_thing._return_to_starting_position.call_count == (
        testcase.return_to_start_calls
    )
    assert scan_thing._perform_final_stitch.call_count == (
        testcase.perform_final_stitch_calls
    )
    assert scan_thing._ongoing_scan.save_scan_data.call_count == (
        testcase.save_scan_data_calls
    )
