#!/usr/bin/env python

# Copyright 2017-present Samsung Electronics Co., Ltd. and other contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import print_function

import re

from common_py.system.filesystem import FileSystem as fs
from common_py.system.executor import Executor as ex
from common_py import path


def resolve_modules(options):
    """ Resolve include/exclude module lists based on command line arguments
        and build config.
    """
    # Load the modules which are always enabled and the include/exclude sets
    build_modules_always = set(options.config['module']['always'])
    build_modules_includes = set(options.config['module']['include'])
    build_modules_excludes = set(options.config['module']['exclude']['all'])

    if options.target_os:
        system_os = options.target_os
        if system_os == 'tizen':
            system_os = 'linux'
        build_modules_excludes |= set(
            options.config['module']['exclude'][system_os])

    # Build options has higher priority than defaults
    build_modules_excludes -= options.iotjs_include_module

    # By default the target included modules are:
    #  - always module set from the build config
    #  - modules specified by the command line argument
    include_modules = set() | build_modules_always
    include_modules |= options.iotjs_include_module

    if not options.iotjs_minimal_profile:
        # Add the include set from the build config to
        # the target include modules set
        include_modules |= build_modules_includes

    # Check if there are any modules which are not allowed to be excluded
    impossible_to_exclude = options.iotjs_exclude_module & build_modules_always
    if impossible_to_exclude:
        ex.fail('Cannot exclude modules which are always enabled: %s' %
                ', '.join(impossible_to_exclude))

    # Finally build up the excluded module set:
    #  - use the command line exclude set
    #  - use the exclude set from the build config
    exclude_modules = options.iotjs_exclude_module | build_modules_excludes

    # Remove the excluded modules from the included modules set
    include_modules -= exclude_modules

    return include_modules, exclude_modules


def analyze_module_dependency(include_modules, exclude_modules):
    analyze_queue = set(include_modules) # copy the set
    analyze_queue.add('iotjs')

    js_modules = { 'native' }
    native_modules = { 'process' }
    while analyze_queue:
        item = analyze_queue.pop()
        js_modules.add(item)
        js_module_path = fs.join(path.PROJECT_ROOT,
                                 'src', 'js', item + '.js')
        if not fs.exists(js_module_path):
            ex.fail('Cannot read file "%s"' % js_module_path)
        with open(js_module_path) as module:
            content = module.read()

        # Pretend to ignore comments in JavaScript
        re_js_comments = "\/\/.*|\/\*.*\*\/";
        content = re.sub(re_js_comments, "", content)

        # Get all required modules
        re_js_module = 'require\([\'\"](.*?)[\'\"]\)'
        required_modules = set(re.findall(re_js_module, content))
        # Check if there is any required modules in the exclude set
        problem_modules = required_modules & exclude_modules
        if problem_modules:
            ex.fail('Cannot exclude module(s) "%s" since "%s" requires them' %
                    (', '.join(problem_modules), item))

        # Add all modules to analytze queue which are not yet analyzed
        analyze_queue |= required_modules - js_modules

        # Get all native modules
        re_native_module = 'process.binding\(process.binding.(.*?)\)'
        native_modules |= set(re.findall(re_native_module, content))

    js_modules.remove('native')

    modules = {'js': sorted(js_modules), 'native': sorted(native_modules)}

    return modules


def _normalize_module_set(argument):
    """ Split up argument via commas and make sure they have a valid value """
    return set([module.strip() for module in argument.split(',')
                if module.strip()])


def _load_options(argv):
    try:
        basestring
    except:
        # in Python 3.x there is no basestring just str
        basestring = str

    # Specify the allowed options for the script
    opts = [
        {'name': 'iotjs-minimal-profile',
         'args': dict(action='store_true', default=False,
            help='Build IoT.js with minimal profile')
        },
        {'name': 'iotjs-include-module',
         'args': dict(action='store', default=set(),
            type=_normalize_module_set,
            help='Specify iotjs modules which should be included '
                 '(format: module_1,module_2,...)')
        },
        {'name': 'iotjs-exclude-module',
         'args': dict(action='store', default=set(),
            type=_normalize_module_set,
            help='Specify iotjs modules which should be excluded '
                 '(format: module_1,module_2,...)')
        },
        {'name': 'mode',
         'args': dict(choices=['verbose', 'cmake-dump'],
            default='verbose',
            help='Execution mode of the script. Choices: %(choices)s '
                 '(default: %(default)s)'
            ),
        },
    ]
    allowed_options = [opt['name'] for opt in opts]

    arg_config = list(filter(lambda x: x.startswith('--config='), argv))
    config_path = path.BUILD_CONFIG_PATH

    if arg_config:
        config_path = arg_config[-1].split('=', 1)[1]

    # Read config file and apply it to argv.
    with open(config_path, 'rb') as f:
        config = json.loads(f.read().decode('ascii'))

    loaded_argv = []
    for opt_key, opt_value in config['build_option'].items():
        if opt_key not in allowed_options:
            continue # ignore any option that is not for us

        if isinstance(opt_value, basestring) and opt_value:
            loaded_argv.append('--%s=%s' % (opt_key, opt_value))
        elif isinstance(opt_value, bool):
            if opt_value:
                loaded_argv.append('--%s' % opt_key)
        elif isinstance(opt_value, int):
            loaded_argv.append('--%s=%s' % (opt_key, opt_value))
        elif isinstance(opt_value, list):
            for val in opt_value:
                loaded_argv.append('--%s=%s' % (opt_key, val))

    # Apply command line argument to argv.
    loaded_argv.extend([arg for arg in argv[1:]
                       if not arg.startswith('--config=')])

    # Build up the argument parser and process the args
    parser = argparse.ArgumentParser()

    for opt in opts:
        parser.add_argument('--%s' % opt['name'], **opt['args'])

    options = parser.parse_args(loaded_argv)
    options.config = config
    options.target_os = config['build_option']['target-os']

    return options


def _main():
    options = _load_options(sys.argv)

    includes, excludes = resolve_modules(options)
    modules = analyze_module_dependency(includes, excludes)

    if options.mode == 'cmake-dump':
        print('IOTJS_JS_MODULES=' + ';'.join(modules['js']))
        print('IOTJS_NATIVE_MODULES=' + ';'.join(modules['native']))
    else:
        print('Selected js modules: %s' % ', '.join(modules['js']))
        print('Selected native modules: %s' % ', '.join(modules['native']))


if __name__ == '__main__':
    import argparse
    import json
    import sys

    _main()
