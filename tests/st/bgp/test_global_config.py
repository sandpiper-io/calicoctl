# Copyright (c) 2015-2016 Tigera, Inc. All rights reserved.
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
from nose.plugins.attrib import attr

from tests.st.test_base import TestBase
from tests.st.utils.docker_host import DockerHost
from tests.st.utils.constants import (DEFAULT_IPV4_ADDR_1, DEFAULT_IPV4_ADDR_2,
                                      DEFAULT_IPV4_POOL_CIDR, LARGE_AS_NUM)
from tests.st.utils.exceptions import CommandExecError
from tests.st.utils.utils import assert_network, assert_profile, \
    assert_number_endpoints, get_profile_name, ETCD_CA, ETCD_CERT, \
    ETCD_KEY, ETCD_HOSTNAME_SSL, ETCD_SCHEME, get_ip, check_bird_status

from .peer import ADDITIONAL_DOCKER_OPTIONS

class TestBGP(TestBase):

    def test_defaults(self):
        """
        Test default BGP configuration commands.
        """
        with DockerHost('host', start_calico=False, dind=False) as host:
            # Check default AS command
            self.assertEquals(host.calicoctl("config get asNumber"), "64512")
            host.calicoctl("config set asNumber 12345")
            self.assertEquals(host.calicoctl("config get asNumber"), "12345")
            with self.assertRaises(CommandExecError):
                host.calicoctl("config set asNumber 99999999999999999999999")
            with self.assertRaises(CommandExecError):
                host.calicoctl("config set asNumber abcde")

            # Check BGP mesh command
            self.assertEquals(host.calicoctl("config get nodeToNodeMesh"), "on")
            host.calicoctl("config set nodeToNodeMesh off")
            self.assertEquals(host.calicoctl("config get nodeToNodeMesh"), "off")
            host.calicoctl("config set nodeToNodeMesh on")
            self.assertEquals(host.calicoctl("config get nodeToNodeMesh"), "on")

    @attr('slow')
    def test_as_num(self):
        """
        Test using different AS number for the node-to-node mesh.

        We run a multi-host test for this as we need to set up real BGP peers.
        """
        with DockerHost('host1',
                        additional_docker_options=ADDITIONAL_DOCKER_OPTIONS,
                        start_calico=False) as host1, \
             DockerHost('host2',
                        additional_docker_options=ADDITIONAL_DOCKER_OPTIONS,
                        start_calico=False) as host2:

            # Set the default AS number.
            host1.calicoctl("config set asNumber %s" % LARGE_AS_NUM)

            # Start host1 using the inherited AS, and host2 using a specified
            # AS (same as default).
            host1.start_calico_node()
            host2.start_calico_node("--as=%s" % LARGE_AS_NUM)

            # Create a network and a couple of workloads on each host.
            network1 = host1.create_network("subnet1", subnet=DEFAULT_IPV4_POOL_CIDR)
            workload_host1 = host1.create_workload("workload1", network=network1, ip=DEFAULT_IPV4_ADDR_1)
            workload_host2 = host2.create_workload("workload2", network=network1, ip=DEFAULT_IPV4_ADDR_2)

            # Allow network to converge
            self.assert_true(workload_host1.check_can_ping(DEFAULT_IPV4_ADDR_2, retries=10))

            # Check connectivity in both directions
            self.assert_ip_connectivity(workload_list=[workload_host1,
                                                       workload_host2],
                                        ip_pass_list=[DEFAULT_IPV4_ADDR_1,
                                                      DEFAULT_IPV4_ADDR_2])

            # Check the BGP status on each host.
            check_bird_status(host1, [("node-to-node mesh", host2.ip, "Established")])
            check_bird_status(host2, [("node-to-node mesh", host1.ip, "Established")])
