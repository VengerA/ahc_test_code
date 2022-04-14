import time
from enum import Enum
from adhoccomputing import GenericModel, Event, Generics, Definitions, Topology, FramerObjects, FrameHandlerBase, ofdm_callback, MacCsmaPPersistentConfigurationParameters, MacCsmaPPersistent, UsrpB210OfdmFlexFramePhy
from ctypes import *


# define your own message types
class ApplicationLayerMessageTypes(Enum):
    BROADCAST = "BROADCAST"

# define your own message header structure
class ApplicationLayerMessageHeader(Generics.GenericMessageHeader):
    pass

# define your own EventTypes 
class UsrpApplicationLayerEventTypes(Enum):
    STARTBROADCAST = "startbroadcast"


# In this part, by using Generic Model provided from adhoccomputing library, an USRP application layer is generated and extended. 
# The main idea behind the adhoccomputing library is meeting the only basic needs for AdHoc Computing. 
# The Code that provided can be extended to cover any kind of protocols, layers, algorithms and etc. 
# In this USRPApplicationLayer, people extended the GenericModel and override the methods:
#  -- __init__ -- on_message_from_top -- on_message_from_bottom
# In addition to that, also new method is added which is on_startbroadcast as you can see below.
class UsrpApplicationLayer(GenericModel):
    # def on_init(self, eventobj: Event):

    def __init__(self, componentname, componentid):
        super().__init__(componentname, componentid)
        self.counter = 0
        # Event handler uses Eventypes to Call Proper Events from other layers or trigger events 
        self.eventhandlers[UsrpApplicationLayerEventTypes.STARTBROADCAST] = self.on_startbroadcast

    def on_message_from_top(self, eventobj: Event):
    # print(f"I am {self.componentname}.{self.componentinstancenumber},sending down eventcontent={eventobj.eventcontent}\n")
        self.send_down(Event(self, Definitions.EventTypes.MFRT, eventobj.eventcontent))

    def on_message_from_bottom(self, eventobj: Event):
        evt = Event(self, Definitions.EventTypes.MFRT, eventobj.eventcontent)
        print(f"I am Node.{self.componentinstancenumber}, received from Node.{eventobj.eventcontent.header.messagefrom} a message: {eventobj.eventcontent.payload}")
        if self.componentinstancenumber == 1:
            evt.eventcontent.header.messageto = 0
            evt.eventcontent.header.messagefrom = 1
        else:
            evt.eventcontent.header.messageto = 1
            evt.eventcontent.header.messagefrom = 0
        evt.eventcontent.payload = eventobj.eventcontent.payload
        #print(f"I am {self.componentname}.{self.componentinstancenumber}, sending down eventcontent={eventobj.eventcontent.payload}\n")
        self.send_down(evt)  # PINGPONG

    def on_startbroadcast(self, eventobj: Event):
        if self.componentinstancenumber == 1:
            hdr = ApplicationLayerMessageHeader(ApplicationLayerMessageTypes.BROADCAST, 1, 0)
        else:
            hdr = ApplicationLayerMessageHeader(ApplicationLayerMessageTypes.BROADCAST, 0, 1)
        self.counter = self.counter + 1

        payload = "BMSG-" + str(self.counter)
        broadcastmessage = Generics.GenericMessage(hdr, payload)
        evt = Event(self, Definitions.EventTypes.MFRT, broadcastmessage)
        # time.sleep(3)
        self.send_down(evt)


# The USRPNode is like a AdHocNode that is provided by adhoccomputing library. It behaves like a 
# container for layers. In this node, we have application - physical and mac components. 
# As you can see we have Connector Types - UP - DOWN and more. These components creates an order between 
# components so that the messaging between components will be handled by send_down -- trigger_event and more.
class UsrpNode(GenericModel):
    counter = 0
    def on_init(self, eventobj: Event):
        pass

    def __init__(self, componentname, componentid):
        # SUBCOMPONENTS

        macconfig = MacCsmaPPersistentConfigurationParameters(0.5)

        self.appl = UsrpApplicationLayer("UsrpApplicationLayer", componentid)
        self.phy = UsrpB210OfdmFlexFramePhy("UsrpB210OfdmFlexFramePhy", componentid)
        self.mac = MacCsmaPPersistent("MacCsmaPPersistent", componentid,  configurationparameters=macconfig, uhd=self.phy.ahcuhd)

        # CONNECTIONS AMONG SUBCOMPONENTS
        self.appl.connect_me_to_component(Definitions.ConnectorTypes.UP, self) #Not required if nodemodel will do nothing
        self.appl.connect_me_to_component(Definitions.ConnectorTypes.DOWN, self.mac)

        self.mac.connect_me_to_component(Definitions.ConnectorTypes.UP, self.appl)
        self.mac.connect_me_to_component(Definitions.ConnectorTypes.DOWN, self.phy)

        # Connect the bottom component to the composite component....
        self.phy.connect_me_to_component(Definitions.ConnectorTypes.UP, self.mac)
        self.phy.connect_me_to_component(Definitions.ConnectorTypes.DOWN, self)

        # self.phy.connect_me_to_component(ConnectorTypes.DOWN, self)
        # self.connect_me_to_component(ConnectorTypes.DOWN, self.appl)

        super().__init__(componentname, componentid)




def main():
    topo = Topology()
    # Note that the Topology has to specific: usrp winslab_b210_0 is run by instance 0 of the component
    # Therefore, the usrps have to have names winslab_b210_x where x \in (0 to nodecount-1)
    # In this topology, we dont have channels between nodes. We handle that part by broadcasting messages 
    # by using USRP devices. However, you can create topologies with custom channels too by using adhoccomputing
    # library. Unfortunatelly, it is not currently compatible with USRPdevices but in upcomping weeks 
    # we will bring that feature too. 
    topo.construct_winslab_topology_without_channels(4, UsrpNode)

    # start funtion in topology generates a forwarding table for network layer operations. However, in this case it 
    # may be unneccesary.
    topo.start()
    i = 0
    while(i < 10):
        topo.nodes[1].appl.send_self(Event(topo.nodes[0], UsrpApplicationLayerEventTypes.STARTBROADCAST, None))
        time.sleep(1)
        i = i + 1


if __name__ == "__main__":
    main()


