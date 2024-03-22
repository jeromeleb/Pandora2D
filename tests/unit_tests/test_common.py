#!/usr/bin/env python
# coding: utf8
#
# Copyright (c) 2024 Centre National d'Etudes Spatiales (CNES).
# Copyright (c) 2024 CS GROUP France
#
# This file is part of PANDORA2D
#
#     https://github.com/CNES/Pandora2D
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""
Test common
"""

# pylint: disable=redefined-outer-name
import os

import numpy as np
import pytest
import xarray as xr
from skimage.io import imsave

from pandora2d import common
from pandora2d.img_tools import create_datasets_from_inputs
from pandora2d import matching_cost, disparity, refinement


class TestSaveDataset:
    """Test save_dataset method"""

    @pytest.fixture
    def create_test_dataset(self):
        """
        Create a test dataset
        """
        row, col = np.full((2, 2), 1), np.full((2, 2), 1)

        dataset_y = xr.Dataset(
            {"row_map": (["row", "col"], row)},
            coords={"row": np.arange(row.shape[0]), "col": np.arange(row.shape[1])},
        )

        dataset_x = xr.Dataset(
            {"col_map": (["row", "col"], col)},
            coords={"row": np.arange(col.shape[0]), "col": np.arange(col.shape[1])},
        )

        dataset = dataset_y.merge(dataset_x, join="override", compat="override")

        return dataset

    def test_save_dataset(self, create_test_dataset, correct_input_cfg):
        """
        Function for testing the dataset_save function
        """

        common.save_dataset(create_test_dataset, correct_input_cfg, "./tests/res_test/")
        assert os.path.exists("./tests/res_test/")

        assert os.path.exists("./tests/res_test/columns_disparity.tif")
        assert os.path.exists("./tests/res_test/row_disparity.tif")

        os.remove("./tests/res_test/columns_disparity.tif")
        os.remove("./tests/res_test/row_disparity.tif")
        os.rmdir("./tests/res_test")


def create_dataset_coords(data_row, data_col, row, col):
    """
    Create xr.Dataset with data_row and data_col as data variables and row and col as coordinates
    """

    data_variables = {"row_map": (("row", "col"), data_row), "col_map": (("row", "col"), data_col)}

    coords = {"row": row, "col": col}

    dataset = xr.Dataset(data_variables, coords)

    return dataset


class TestDatasetDispMaps:
    """Test dataset_disp_maps method"""

    @pytest.fixture()
    def left_image(self, tmp_path):
        """
        Create a fake image to test dataset_disp_maps method
        """
        image_path = tmp_path / "left_img.png"
        data = np.full((10, 10), 1, dtype=np.uint8)
        imsave(image_path, data)

        return image_path

    @pytest.fixture()
    def right_image(self, tmp_path):
        """
        Create a fake image to test dataset_disp_maps method
        """
        image_path = tmp_path / "right_img.png"
        data = np.full((10, 10), 1, dtype=np.uint8)
        imsave(image_path, data)

        return image_path

    @pytest.mark.parametrize(
        ["row", "col"],
        [
            pytest.param(
                np.arange(10),
                np.arange(10),
                id="Classic case",
            ),
            pytest.param(
                np.arange(10, 20),
                np.arange(20, 30),
                id="ROI case",
            ),
            pytest.param(
                np.arange(2, 12),
                np.arange(2, 12, 2),
                id="Step in col",
            ),
            pytest.param(
                np.arange(2, 12, 2),
                np.arange(2, 12, 2),
                id="Step in row",
            ),
        ],
    )
    def test_dataset_disp_maps(self, row, col):
        """
        Test for dataset_disp_maps method
        """

        dataset_test = create_dataset_coords(
            np.full((len(row), len(col)), 1), np.full((len(row), len(col)), 1), row, col
        )

        # create dataset with dataset_disp_maps function
        disparity_maps = common.dataset_disp_maps(
            np.full((len(row), len(col)), 1),
            np.full((len(row), len(col)), 1),
            dataset_test.coords,
            {"invalid_disp": -9999},
        )

        assert disparity_maps.equals(dataset_test)

    @pytest.mark.parametrize(
        ["coord_value", "coord", "string_match"],
        [
            pytest.param(
                np.arange(10),
                "row",
                "The col coordinate does not exist",
                id="No col coordinates",
            ),
            pytest.param(
                np.arange(10),
                "col",
                "The row coordinate does not exist",
                id="No row coordinates",
            ),
        ],
    )
    def test_dataset_disp_maps_fails_with_missing_coords(self, coord_value, coord, string_match):
        """
        Test that dataset_disp_maps method fails when one of the coordinates is missing
        """

        # create a dataset with only one of the two required coordinates
        data_variables = {
            "row_map": ((coord), np.full((len(coord_value)), 1)),
            "col_map": ((coord), np.full((len(coord_value)), 1)),
        }

        coords = {coord: coord_value}

        dataset_test = xr.Dataset(data_variables, coords)

        # create dataset with dataset_disp_maps function
        with pytest.raises(ValueError, match=string_match):
            common.dataset_disp_maps(
                np.full((len(coord_value)), 1),
                np.full((len(coord_value)), 1),
                dataset_test.coords,
                {"invalid_disp": -9999},
            )

    @pytest.mark.filterwarnings("ignore::UserWarning")
    @pytest.mark.parametrize(
        ["roi", "step"],
        [
            pytest.param(
                {"col": {"first": 3, "last": 5}, "row": {"first": 3, "last": 5}, "margins": [2, 2, 2, 2]},
                [1, 1],
                id="ROI in image",
            ),
            pytest.param(
                {"col": {"first": 3, "last": 5}, "row": {"first": 3, "last": 5}, "margins": [2, 2, 2, 2]},
                [2, 1],
                id="ROI in image and step=2 for rows",
            ),
            pytest.param(
                {},
                [1, 1],
                id="No ROI",
            ),
        ],
    )
    def test_dataset_disp_maps_with_pipeline_computation(self, roi, step, left_image, right_image):
        """
        Test for dataset_disp_maps method after computation of disparity maps and refinement step
        """

        # input configuration
        input_cfg = {
            "input": {
                "left": {
                    "img": left_image,
                    "nodata": -9999,
                },
                "right": {
                    "img": right_image,
                    "nodata": -9999,
                },
                "col_disparity": [0, 4],
                "row_disparity": [-2, 2],
            }
        }

        img_left, img_right = create_datasets_from_inputs(input_cfg["input"], roi=roi)

        cfg = {"matching_cost_method": "zncc", "window_size": 3, "step": step}

        matching_cost_matcher = matching_cost.MatchingCost(cfg)

        matching_cost_matcher.allocate_cost_volume_pandora(
            img_left=img_left,
            img_right=img_right,
            grid_min_col=np.full((3, 3), 0),
            grid_max_col=np.full((3, 3), 4),
            cfg=cfg,
        )

        # compute cost volumes
        cvs = matching_cost_matcher.compute_cost_volumes(
            img_left=img_left,
            img_right=img_right,
            grid_min_col=np.full((3, 3), 0),
            grid_max_col=np.full((3, 3), 4),
            grid_min_row=np.full((3, 3), -2),
            grid_max_row=np.full((3, 3), 2),
        )

        cfg_disp = {"disparity_method": "wta", "invalid_disparity": -9999}
        disparity_matcher = disparity.Disparity(cfg_disp)
        # compute disparity maps
        delta_row, delta_col = disparity_matcher.compute_disp_maps(cvs)

        # create dataset with dataset_disp_maps function
        disparity_maps = common.dataset_disp_maps(delta_row, delta_col, cvs.coords, {"invalid_disp": -9999})

        interpolation = refinement.AbstractRefinement({"refinement_method": "interpolation"})  # type: ignore[abstract]
        # compute refined disparity maps
        delta_x, delta_y = interpolation.refinement_method(cvs, disparity_maps, img_left, img_right)

        # create dataset with dataset_disp_maps function
        refined_disparity_maps = common.dataset_disp_maps(delta_x, delta_y, disparity_maps.coords)

        # create ground truth with create_dataset_coords method
        dataset_ground_truth = create_dataset_coords(delta_x, delta_y, disparity_maps.row, disparity_maps.col)

        assert refined_disparity_maps.equals(dataset_ground_truth)
