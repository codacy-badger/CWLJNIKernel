import os
import subprocess
import sys
import traceback
from pathlib import Path
from typing import (
    Dict,
    List,
    Optional,
    Tuple,
    NoReturn)
from uuid import uuid4, UUID

from cwltool import process as cwl_process
from cwltool.context import RuntimeContext, LoadingContext
from cwltool.cwlrdf import printdot
from cwltool.factory import Factory
from cwltool.load_tool import default_loader
from ruamel import yaml

from .IOManager import IOFileManager


class CoreExecutor:

    def __init__(self, file_manager: IOFileManager):
        self.file_manager = file_manager
        self._workflow_path = None
        self._data_paths = []

    def set_data(self, data: List[str]) -> List[str]:
        self._data_paths = [self.file_manager.write(f'{str(uuid4())}.yml', d.encode()) for d in data]
        return self._data_paths

    def set_workflow(self, workflow_str: str) -> str:
        """
        :param workflow_str: the cwl
        :return: the path where we executor stored the workflow
        """
        self._workflow_path = self.file_manager.write(f'{str(uuid4())}.cwl', workflow_str.encode())
        return self._workflow_path

    def execute(self) -> Tuple[UUID, Dict, Optional[Exception]]:
        """
        :return: Run ID, dict with new files, exception if there is any
        """
        run_id = uuid4()

        data, executable = self.__init_workflow__()
        try:
            result: Dict = executable(**data)
            from io import StringIO

            return run_id, result, None
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            return run_id, {}, e

    def __init_workflow__(self):
        runtime_context = RuntimeContext()
        runtime_context.outdir = self.file_manager.ROOT_DIRECTORY
        runtime_context.basedir = self.file_manager.ROOT_DIRECTORY
        runtime_context.default_stdin = subprocess.DEVNULL
        runtime_context.default_stdout = subprocess.DEVNULL
        runtime_context.default_stderr = subprocess.DEVNULL
        loading_context = LoadingContext()
        loading_context.loader = default_loader(loading_context.fetcher_constructor)
        with open(self._workflow_path) as f:
            cwl_version = yaml.load(f)['cwlVersion']
        loading_context.loader.ctx = cwl_process.get_schema(cwl_version)[0].ctx
        # process.get_schema(cwlVersion)[:2][0]
        os.chdir(self.file_manager.ROOT_DIRECTORY)
        factory = Factory(runtime_context=runtime_context, loading_context=loading_context)
        executable = factory.make(self._workflow_path)
        data = {}
        for data_file in self._data_paths:
            with open(data_file) as f:
                new_data = yaml.load(f, Loader=yaml.Loader)
                data = {**new_data, **data}
        return data, executable

    @classmethod
    def validate_input_files(cls, yaml_input: Dict, cwd: Path) -> NoReturn:
        for arg in yaml_input:
            if isinstance(yaml_input[arg], dict) and 'class' in yaml_input[arg] and yaml_input[arg]['class'] == 'File':
                # TODO: check about path vs location
                selector = 'location' if 'location' in yaml_input[arg] else 'path'
                file_path = Path(yaml_input[arg][selector])
                if not file_path.is_absolute():
                    file_path = cwd / file_path
                if not file_path.exists():
                    raise FileNotFoundError(file_path)
